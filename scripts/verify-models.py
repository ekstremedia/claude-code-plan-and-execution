#!/usr/bin/env python3
"""Show which model a skill invocation actually ran on, from a session transcript.

The `model` field on assistant messages records the session's configured model,
not the one that ran the turn — it will happily say "opus" for 500 turns while a
`model: sonnet` skill is executing. The authoritative record is the
`command_permissions` attachment the harness writes when a skill is invoked.

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


def unqualify(name):
    """`plan-and-execute:implementer` -> `implementer`."""
    return name.rsplit(":", 1)[-1]


def scan(path):
    """Return a summary dict for one transcript, or None if unreadable."""
    invocations = []
    delegations = Counter()
    logged_models = Counter()
    cwd = None
    first_ts = None

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

            msg = rec.get("message")
            if not isinstance(msg, dict):
                continue

            if rec.get("type") == "assistant" and not rec.get("isSidechain"):
                if msg.get("model"):
                    logged_models[msg["model"]] += 1

            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("name") == "Agent":
                    inp = block.get("input") or {}
                    delegations[inp.get("subagent_type") or "?"] += 1

    return {
        "path": path,
        "cwd": cwd,
        "ts": first_ts,
        "invocations": invocations,
        "delegations": delegations,
        "logged_models": logged_models,
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
    for w in warnings:
        print(f"  WARNING: {w}")

    if summary["logged_models"]:
        shown = ", ".join(
            f"{m} x{n}" for m, n in summary["logged_models"].most_common()
        )
        print(f"  message.model (session config, NOT effective): {shown}")
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
