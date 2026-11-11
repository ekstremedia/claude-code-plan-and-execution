#!/usr/bin/env python3
"""Show what each worker is doing, in its row under the prompt.

Claude Code keeps a subagent's work inside the subagent: the main chat shows one
row per running worker — `name · description · token count` — and nothing of
what it reads, edits or runs. The `subagentStatusLine` setting lets a command
rewrite those rows. This is that command. A row becomes:

    implementer · Phase 2: scan reader · edit app/Ai/ScanLineParser.php · 9 files changed · test-php ok · 41.2k tok · 12m

Wire it up in the project's `.claude/settings.json`
(`templates/settings.snippet.json` carries the entry):

    "subagentStatusLine": {
      "type": "command",
      "command": "python3 \\"$CLAUDE_PROJECT_DIR/.claude/plan-and-execute/subagent-statusline.py\\""
    }

How it works. Claude Code runs the command every few seconds while a worker is
visible, with one JSON object on stdin: the session's `transcript_path`, the
usable `columns`, and a `tasks` array whose `id` is the worker's agent id. The
worker's own transcript is `<session>/subagents/agent-<id>.jsonl`; this script
reads it and prints one `{"id", "content"}` line per row it rewrites. A worker
whose transcript cannot be read keeps its default row.

A transcript reaches megabytes on a long phase, so each tick parses only what
was appended since the last one. The running state lives in a small cache file
per worker under the system temp directory.

Measured on Claude Code 2.1.322: `tasks[].id` is the agent id in the transcript
filename, the command runs with the project as its working directory and
`CLAUDE_PROJECT_DIR` set, and it ticked five times in twenty seconds.

Standard library only. Set NO_COLOR to drop the dimming.
"""

import json
import os
import re
import sys
import tempfile
import time

# A file change made with these tools names its file in the call itself.
EDIT_TOOLS = {"Edit": "edit", "MultiEdit": "edit", "NotebookEdit": "edit", "Write": "write"}

# The test and check wrappers the worker agents are written against
# (templates/bin/test-example.sh). Adapt if this project's are named otherwise.
CHECK_RE = re.compile(r"(?:^|[\s;&|(/])bin/((?:test|check)-[A-Za-z0-9_.-]+)")

CACHE_VERSION = 1
CACHE_MAX_AGE = 24 * 3600
SEP = " · "


# ── reading the worker's transcript ──────────────────────────────────────────


def new_state():
    """The running summary of one worker's transcript."""
    return {
        "v": CACHE_VERSION,
        "offset": 0,       # bytes of the transcript already parsed
        "seen": [],        # tool_use ids counted — a streamed message repeats its blocks
        "tools": 0,
        "files": [],       # every file changed, in first-touched order
        "activity": "",    # what the worker did last
        "checks": {},      # tool_use id -> wrapper name, awaiting a result
        "check": "",       # the last finished check, e.g. "test-php ok"
    }


def rel(path, cwd):
    """A path the way the row shows it: relative to the worker's directory."""
    if not path:
        return ""
    if cwd and (path == cwd or path.startswith(cwd.rstrip("/") + "/")):
        return os.path.relpath(path, cwd)
    home = os.path.expanduser("~")
    if path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path


def one_line(text):
    """The first line of a command, whitespace collapsed."""
    for line in str(text).splitlines():
        line = " ".join(line.split())
        if line:
            return line
    return ""


def describe(name, inp, cwd):
    """One short phrase for a tool call."""
    if name in EDIT_TOOLS:
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        return f"{EDIT_TOOLS[name]} {rel(path, cwd)}"
    if name == "Read":
        return f"read {rel(inp.get('file_path') or '', cwd)}"
    if name == "Bash":
        return f"$ {one_line(inp.get('command') or '')}"
    if name in ("Grep", "Glob"):
        return f"{name.lower()} {inp.get('pattern') or ''}"
    if name in ("Agent", "Task"):
        return f"delegating to {inp.get('subagent_type') or 'a subagent'}"
    if name == "Skill":
        return f"skill {inp.get('skill') or ''}"
    if name == "SubagentHandback":
        return "writing its report"
    if name.startswith("mcp__"):
        parts = name.split("__")
        return ":".join(p for p in parts[1:] if p)
    return name


def note_file(state, path, cwd):
    """Record a changed file once."""
    shown = rel(path, cwd)
    if shown and shown not in state["files"]:
        state["files"].append(shown)
    return shown


def feed(state, rec, cwd):
    """Fold one transcript record into the running state."""
    msg = rec.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, list):
        return

    for block in content:
        if not isinstance(block, dict):
            continue

        if block.get("type") == "tool_use":
            block_id = block.get("id") or ""
            if block_id in state["seen"]:
                continue
            state["seen"].append(block_id)
            state["tools"] += 1
            name = block.get("name") or "?"
            inp = block.get("input") if isinstance(block.get("input"), dict) else {}
            state["activity"] = describe(name, inp, cwd)
            if name in EDIT_TOOLS:
                note_file(state, inp.get("file_path") or inp.get("notebook_path"), cwd)
            elif name == "Bash":
                found = CHECK_RE.findall(inp.get("command") or "")
                if found:
                    state["checks"][block_id] = found[-1]

        elif block.get("type") == "tool_result":
            wrapper = state["checks"].pop(block.get("tool_use_id") or "", None)
            if wrapper:
                body = block.get("content")
                if isinstance(body, list):
                    body = " ".join(
                        b.get("text", "") for b in body if isinstance(b, dict)
                    )
                failed = bool(block.get("is_error")) or one_line(body or "").startswith("FAIL")
                state["check"] = f"{wrapper} {'FAIL' if failed else 'ok'}"

    # A file changed from the shell — a heredoc, sed -i, a script — names no
    # file in the call. Where the harness worked the change out, it records it
    # on the result as `bashEditDiff`.
    result = rec.get("toolUseResult")
    diff = result.get("bashEditDiff") if isinstance(result, dict) else None
    files = diff.get("files") if isinstance(diff, dict) else None
    if isinstance(files, list):
        last = ""
        for entry in files:
            if isinstance(entry, dict) and entry.get("filePath"):
                last = note_file(state, entry["filePath"], cwd) or last
        if last:
            state["activity"] = f"edit {last}"


def advance(state, transcript, cwd):
    """Parse whatever was appended to the transcript since the last tick."""
    size = os.path.getsize(transcript)
    if size < state["offset"]:
        # The file shrank: not the transcript this state was built from.
        fresh = new_state()
        state.clear()
        state.update(fresh)
    if size == state["offset"]:
        return
    with open(transcript, "rb") as fh:
        fh.seek(state["offset"])
        chunk = fh.read()
    # A record still being written has no newline yet; leave it for next tick.
    end = chunk.rfind(b"\n")
    if end < 0:
        return
    state["offset"] += end + 1
    for raw in chunk[: end + 1].splitlines():
        # Most of a transcript's bytes are request logs and attachments. Only
        # assistant and user records carry tool calls and their results.
        if b'"type":"assistant"' not in raw and b'"type":"user"' not in raw:
            continue
        try:
            rec = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("type") in ("assistant", "user"):
            feed(state, rec, cwd)


# ── the cache between ticks ──────────────────────────────────────────────────


def cache_dir():
    """A private per-user directory for the per-worker state files."""
    uid = os.getuid() if hasattr(os, "getuid") else "user"
    path = os.path.join(tempfile.gettempdir(), f"plan-and-execute-statusline-{uid}")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def load_state(path):
    """The cached state for one worker, or a fresh one."""
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
        if isinstance(state, dict) and state.get("v") == CACHE_VERSION:
            return state
    except (OSError, ValueError):
        pass
    return new_state()


def save_state(path, state):
    """Write the state atomically: ticks can overlap and be cancelled."""
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def prune(directory):
    """Drop state files of workers long finished."""
    cutoff = time.time() - CACHE_MAX_AGE
    try:
        for entry in os.scandir(directory):
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                os.unlink(entry.path)
    except OSError:
        pass


# ── drawing the row ──────────────────────────────────────────────────────────


def fmt_tokens(n):
    """999, 41.2k, 1.3M."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def fmt_elapsed(seconds):
    """45s, 12m, 1h04m."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"


def clip(text, width, keep_tail=False):
    """Shorten to width with an ellipsis; a path keeps its tail."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "…"
    return "…" + text[-(width - 1):] if keep_tail else text[: width - 1] + "…"


def row(task, state, columns, color):
    """Compose one row body that fits in `columns`."""
    status = task.get("status") or ""
    head = task.get("agentType") or task.get("name") or "agent"
    what = task.get("label") or task.get("description") or ""
    activity = state["activity"] if status == "running" else status
    is_path = activity.split(" ", 1)[0] in ("edit", "write", "read")

    files = ""
    if state["files"]:
        n = len(state["files"])
        files = f"{n} file{'s' if n != 1 else ''} changed"
    check = state["check"]
    tokens = ""
    if isinstance(task.get("tokenCount"), (int, float)) and task["tokenCount"]:
        tokens = f"{fmt_tokens(int(task['tokenCount']))} tok"
    elapsed = ""
    if isinstance(task.get("startTime"), (int, float)):
        elapsed = fmt_elapsed(time.time() - task["startTime"] / 1000)

    def width():
        shown = [p for p in (head, what, activity, files, check, tokens, elapsed) if p]
        return sum(len(p) for p in shown) + len(SEP) * (len(shown) - 1)

    def squeeze(text, floor, keep_tail=False):
        """Clip text by the current overflow, but not below `floor`."""
        over = width() - columns
        if over <= 0 or len(text) <= floor:
            return text
        return clip(text, max(floor, len(text) - over), keep_tail)

    # Too wide: give up the least useful parts first. What the worker is doing
    # and what it has changed go last.
    what = squeeze(what, 24)
    if width() > columns:
        tokens = ""
    if width() > columns:
        elapsed = ""
    activity = squeeze(activity, 32, is_path)
    what = squeeze(what, 8)
    if width() > columns:
        what = ""
    if width() > columns:
        check = "" if not check.endswith(" FAIL") else check
    activity = squeeze(activity, 12, is_path)
    if width() > columns:
        files = ""
    if width() > columns:
        activity = ""
    head = squeeze(head, 1)

    dim, bold, reset = ("\x1b[2m", "\x1b[1m", "\x1b[0m") if color else ("", "", "")
    parts = [f"{bold}{head}{reset}", what, activity, files]
    if check:
        parts.append(f"{bold}{check}{reset}" if check.endswith(" FAIL") else check)
    parts.extend(f"{dim}{m}{reset}" for m in (tokens, elapsed) if m)
    return f"{dim}{SEP}{reset}".join(p for p in parts if p)


def main():
    """Read the tasks on stdin, print one override line per readable worker."""
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(data, dict):
        return 0
    tasks = data.get("tasks")
    transcript = data.get("transcript_path")
    if not isinstance(tasks, list) or not isinstance(transcript, str):
        return 0

    session_dir = transcript[: -len(".jsonl")] if transcript.endswith(".jsonl") else transcript
    session = os.path.basename(session_dir)
    columns = data.get("columns") if isinstance(data.get("columns"), int) else 100
    color = not os.environ.get("NO_COLOR")
    directory = cache_dir()
    prune(directory)

    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        # The id becomes part of two filenames; take only what an agent id is.
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", task_id):
            continue
        worker = os.path.join(session_dir, "subagents", f"agent-{task_id}.jsonl")
        if not os.path.isfile(worker):
            continue
        cache = os.path.join(directory, f"{session}-{task_id}.json")
        try:
            state = load_state(cache)
            before = state["offset"]
            advance(state, worker, task.get("cwd") or data.get("cwd") or "")
            if state["offset"] != before:
                save_state(cache, state)
            content = row(task, state, columns, color)
        except (OSError, KeyError, TypeError, ValueError):
            continue  # leave this row to the default rendering
        print(json.dumps({"id": task_id, "content": content}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
