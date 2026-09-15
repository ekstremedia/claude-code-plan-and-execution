#!/usr/bin/env python3
"""Show which model a skill invocation actually ran on, from a session transcript.

The authoritative record of a skill's pin is the `command_permissions`
attachment the harness writes when the skill is invoked. The `model` field on
assistant messages is not that record: up to 2.1.239 it logged the session's
configured model regardless of the pin, and on 2.1.259 it logged the effective
model.

A skill's `model:`/`effort:` pin also only applies for the current turn. A
backgrounded subagent's completion arrives as a `task-notification` user record,
which starts a new turn on the session model at the session effort — so the
script watches the top-level `effort` field (present on every assistant record)
and reports the first record where the pin was lost.

Also sums token usage per tier: the main thread from the session transcript,
and each worker from its own transcript under `<session>/subagents/`, grouped
by the `agentType` in the adjacent `.meta.json`. Usage on a streamed message
grows across its records, so records are deduplicated by message id and the
last one wins. Output tokens include thinking tokens.

Usage:
  verify-models.py                    sweep ~/.claude/projects/
  verify-models.py SESSION.jsonl ...  inspect specific transcripts
  verify-models.py --all              sweep, including sessions with no model pin

Standard library only; `jq` is not assumed.
"""

import glob
import json
import os
import sys
from collections import Counter

OURS = {
    "implementer",
    "quick-implementer",
    "plan-reviewer",
    "planning-researcher",
}
# Search agents that inherit the session model — using one for breadth-first
# research defeats the cheap researcher tier.
INHERITS_SESSION_MODEL = {"Explore", "general-purpose", "Plan"}

USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def sum_usage(usage_by_id):
    """Collapse {message id: last-seen usage} into one totals dict."""
    totals = dict.fromkeys(USAGE_KEYS, 0)
    for u in usage_by_id.values():
        for k in USAGE_KEYS:
            v = u.get(k)
            if isinstance(v, (int, float)):
                totals[k] += int(v)
    return totals


def fmt_tok(n):
    """Format a token count as 999, 9.9k, 9.9M, 99M."""
    if n >= 10_000_000:
        return f"{n / 1_000_000:.0f}M"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def usage_line(t):
    """One aligned out/in/cache line for a usage totals dict."""
    return (
        f"out {fmt_tok(t['output_tokens']):>7}   "
        f"in {fmt_tok(t['input_tokens']):>7}   "
        f"cache-read {fmt_tok(t['cache_read_input_tokens']):>7}   "
        f"cache-new {fmt_tok(t['cache_creation_input_tokens']):>7}"
    )


def scan_subagents(path):
    """Aggregate per-agent-type token usage from <session>/subagents/.

    Each subagent transcript is one worker run; the adjacent
    `agent-<id>.meta.json` names its agentType. The subagent transcript's own
    usage records are the worker's spend, which never appears in the parent
    transcript.
    """
    base = path[:-len(".jsonl")] if path.endswith(".jsonl") else path
    out = {}
    for sub in sorted(glob.glob(os.path.join(base, "subagents", "agent-*.jsonl"))):
        atype = None
        try:
            with open(sub[: -len(".jsonl")] + ".meta.json") as mh:
                meta = json.load(mh)
            if isinstance(meta, dict):
                atype = meta.get("agentType")
        except (OSError, ValueError):
            pass
        atype = atype or "<no meta.json>"

        usage_by_id = {}
        models = Counter()
        try:
            fh = open(sub, errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict) or rec.get("type") != "assistant":
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict):
                    continue
                if msg.get("model"):
                    models[msg["model"]] += 1
                u = msg.get("usage")
                if isinstance(u, dict) and msg.get("id"):
                    usage_by_id[msg["id"]] = u

        entry = out.setdefault(
            atype,
            {"runs": 0, "usage": dict.fromkeys(USAGE_KEYS, 0), "models": Counter()},
        )
        entry["runs"] += 1
        entry["models"].update(models)
        for k, v in sum_usage(usage_by_id).items():
            entry["usage"][k] += v
    return out


def unqualify(name):
    """`plan-and-execute:implementer` -> `implementer`."""
    return name.rsplit(":", 1)[-1]


def scan(path):
    """Return a summary dict for one transcript, or None if unreadable."""
    invocations = []
    delegations = Counter()
    logged_models = Counter()
    usage_by_id = {}
    cwd = None
    first_ts = None
    task_notifications = 0
    pin_drops = []
    # Pin tracking: a command_permissions record arms the watch, the next
    # assistant record sets the baseline, and the first record whose effort or
    # model differs from it is where the pin was lost.
    baseline = None
    watching = False
    last_user_kind = None

    try:
        fh = open(path, errors="replace")
    except OSError:
        return None

    with fh:
        for line in fh:
            if '"' not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue

            cwd = cwd or rec.get("cwd")
            first_ts = first_ts or rec.get("timestamp")

            att = rec.get("attachment")
            if isinstance(att, dict) and att.get("type") == "command_permissions":
                invocations.append(
                    {
                        "model": att.get("model"),
                        "tools": att.get("allowedTools") or [],
                        "ts": rec.get("timestamp"),
                    }
                )
                if att.get("model"):
                    baseline = None
                    watching = True

            if rec.get("type") == "user":
                origin = rec.get("origin")
                kind = origin.get("kind") if isinstance(origin, dict) else None
                last_user_kind = kind
                if kind == "task-notification":
                    task_notifications += 1

            msg = rec.get("message")
            if not isinstance(msg, dict):
                continue

            if rec.get("type") == "assistant" and not rec.get("isSidechain"):
                if watching:
                    state = (rec.get("effort"), msg.get("model"))
                    if baseline is None:
                        baseline = state
                    elif state != baseline:
                        pin_drops.append(
                            {
                                "from": baseline,
                                "to": state,
                                "ts": rec.get("timestamp"),
                                "after_notification":
                                    last_user_kind == "task-notification",
                            }
                        )
                        watching = False
                if msg.get("model"):
                    logged_models[msg["model"]] += 1
                u = msg.get("usage")
                if isinstance(u, dict) and msg.get("id"):
                    # A streamed message appears as several records whose
                    # usage grows; the last record for an id is the final one.
                    usage_by_id[msg["id"]] = u

            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("name") == "Agent":
                    inp = block.get("input") or {}
                    name = inp.get("subagent_type") or "?"
                    delegations[name] += 1

    return {
        "path": path,
        "cwd": cwd,
        "ts": first_ts,
        "invocations": invocations,
        "delegations": delegations,
        "logged_models": logged_models,
        "usage": sum_usage(usage_by_id),
        "task_notifications": task_notifications,
        "pin_drops": pin_drops,
    }


def interesting(summary):
    if any(i["model"] for i in summary["invocations"]):
        return True
    return any(unqualify(a) in OURS for a in summary["delegations"])


def report(summary):
    session = os.path.basename(summary["path"]).split(".")[0]
    head = f"=== {session[:8]}"
    if summary["cwd"]:
        head += f"  {summary['cwd']}"
    if summary["ts"]:
        head += f"  {summary['ts'][:16]}"
    print(head)

    if summary["invocations"]:
        print("  skill invocations (command_permissions — authoritative):")
        for inv in summary["invocations"]:
            model = inv["model"] or "<none — skill declares no model:>"
            tools = ", ".join(inv["tools"]) if inv["tools"] else "<unrestricted>"
            when = (inv["ts"] or "")[11:16]
            print(f"    {when}  model={model}")
            print(f"           allowedTools={tools}")
    else:
        print("  skill invocations: none")

    if summary["delegations"]:
        parts = [
            f"{name} x{n}" for name, n in summary["delegations"].most_common()
        ]
        print("  delegations: " + ", ".join(parts))

    if summary.get("task_notifications"):
        print(
            f"  task-notifications: {summary['task_notifications']} "
            f"(each one starts a new turn)"
        )

    warnings = []
    for name, n in summary["delegations"].items():
        if name in INHERITS_SESSION_MODEL:
            warnings.append(
                f"{name} x{n} inherits the session model — a research delegation "
                f"here bypasses planning-researcher and runs at planner rates"
            )
        if ":" in name and unqualify(name) in OURS:
            warnings.append(
                f"{name} is the plugin copy — plugin agents drop permissionMode, "
                f"so a read-only agent is only prompt-enforced"
            )
    for drop in summary.get("pin_drops", []):
        (from_effort, from_model), (to_effort, to_model) = drop["from"], drop["to"]
        changed = []
        if from_effort != to_effort:
            changed.append(f"effort {from_effort}→{to_effort}")
        if from_model != to_model:
            changed.append(f"model {from_model}→{to_model}")
        cause = (
            "following a task-notification"
            if drop["after_notification"]
            else "with no task-notification immediately before it"
        )
        warnings.append(
            f"{' ('.join(changed)}{')' if len(changed) > 1 else ''} at "
            f"{(drop['ts'] or '')[11:16]} {cause} — the skill pin was dropped; "
            f"the rest of the run ran at the session model/effort"
        )
    for w in warnings:
        print(f"  WARNING: {w}")

    subagents = scan_subagents(summary["path"])
    main_usage = summary.get("usage") or {}
    if main_usage.get("output_tokens") or subagents:
        print("  tokens (usage records, deduped by message id; out includes thinking):")
        width = max(
            [len("main thread")]
            + [len(f"{t} x{e['runs']}") for t, e in subagents.items()]
        )
        print(f"    {'main thread':<{width}}   {usage_line(main_usage)}")
        worker_out = 0
        for atype, entry in sorted(
            subagents.items(), key=lambda kv: -kv[1]["usage"]["output_tokens"]
        ):
            label = f"{atype} x{entry['runs']}"
            models = ",".join(m for m, _ in entry["models"].most_common())
            print(
                f"    {label:<{width}}   {usage_line(entry['usage'])}"
                + (f"   [{models}]" if models else "")
            )
            worker_out += entry["usage"]["output_tokens"]
        total_out = worker_out + main_usage.get("output_tokens", 0)
        if worker_out and total_out:
            print(
                f"    worker share of output tokens: "
                f"{100 * worker_out / total_out:.0f}%"
            )

    if summary["logged_models"]:
        shown = ", ".join(
            f"{m} x{n}" for m, n in summary["logged_models"].most_common()
        )
        print(f"  message.model (version-dependent, NOT the pin record): {shown}")
    print()


def main(argv):
    args = [a for a in argv if not a.startswith("-")]
    flags = {a for a in argv if a.startswith("-")}

    if "-h" in flags or "--help" in flags:
        print(__doc__.strip())
        return 0

    if args:
        paths = []
        for a in args:
            paths.extend(sorted(glob.glob(a)) or [a])
        show_all = True
    else:
        root = os.path.expanduser("~/.claude/projects")
        paths = sorted(glob.glob(os.path.join(root, "*", "*.jsonl")))
        show_all = "--all" in flags
        if not paths:
            print(f"no transcripts under {root}", file=sys.stderr)
            return 1

    shown = 0
    for path in paths:
        summary = scan(path)
        if summary is None:
            print(f"unreadable: {path}", file=sys.stderr)
            continue
        if show_all or interesting(summary):
            report(summary)
            shown += 1

    if not shown:
        print("no sessions with a model-pinned skill invocation found.")
        print("re-run with --all to list every session.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
