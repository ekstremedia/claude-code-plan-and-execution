#!/usr/bin/env python3
"""Repo lint — the repository's own contracts as checks, so drift fails CI.

- every agent and skill carries the frontmatter its role requires
- the two read-only agents keep `permissionMode: plan`
- nothing declares keys the harness accepts and ignores (`maxTurns` — measured,
  see docs/gotchas.md)
- the plugin manifests and the settings snippet parse as JSON
- every relative markdown link points at a file that exists

Standard library only. Exit 1 on any finding.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

READONLY_AGENTS = {"planning-researcher", "plan-reviewer"}
INERT_KEYS = {"maxTurns"}

problems = []


def problem(path, msg):
    """Record one finding against a repo-relative path."""
    problems.append(f"{os.path.relpath(path, ROOT)}: {msg}")


def frontmatter(path):
    """Parse the flat `key: value` block between the first two `---` fences."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fm
        m = re.match(r"^([A-Za-z][A-Za-z-]*):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return None  # unterminated


def check_common(path, fm):
    """Rules that apply to every frontmatter block, agent or skill."""
    for key in sorted(INERT_KEYS & fm.keys()):
        problem(path, f"declares {key}: — accepted and ignored by the harness; remove it")


def check_agent(path):
    """An agent must carry its role's frontmatter contract."""
    name = os.path.basename(path)[: -len(".md")]
    fm = frontmatter(path)
    if fm is None:
        problem(path, "missing or unterminated frontmatter")
        return
    for key in ("name", "description", "tools", "model"):
        if not fm.get(key):
            problem(path, f"frontmatter lacks {key}:")
    if fm.get("name") and fm["name"] != name:
        problem(path, f"name: {fm['name']!r} does not match filename {name!r}")
    if name in READONLY_AGENTS and fm.get("permissionMode") != "plan":
        problem(path, "read-only agent without permissionMode: plan")
    check_common(path, fm)


def check_skill(path):
    """A skill must stay pinned, gated, and (for execute-plan) Write-less."""
    name = os.path.basename(os.path.dirname(path))
    fm = frontmatter(path)
    if fm is None:
        problem(path, "missing or unterminated frontmatter")
        return
    for key in ("name", "description", "model", "effort"):
        if not fm.get(key):
            problem(path, f"frontmatter lacks {key}:")
    if fm.get("disable-model-invocation") != "true":
        problem(path, "lacks disable-model-invocation: true — the body would load in every session")
    if name == "execute-plan" and "Write" not in fm.get("disallowed-tools", ""):
        problem(path, "execute-plan must keep Write in disallowed-tools")
    if name == "make-plan" and not fm.get("allowed-tools"):
        problem(path, "make-plan must declare allowed-tools")
    check_common(path, fm)


def check_json(path):
    """A required JSON manifest must exist and parse."""
    try:
        with open(path, encoding="utf-8") as fh:
            json.load(fh)
    except FileNotFoundError:
        problem(path, "required JSON file is missing")
    except (OSError, ValueError) as e:
        problem(path, f"cannot read or parse JSON: {e}")


def check_links(path):
    """Every relative markdown link must point at an existing file."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for m in re.finditer(r"\]\(([^)\s]+)\)", text):
        href = m.group(1)
        if href.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = href.split("#", 1)[0]
        if not target:
            continue
        resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
        if not os.path.isfile(resolved):
            problem(path, f"relative link target missing: {href}")


def main():
    """Run every check; exit 1 if anything was found."""
    import glob

    for f in sorted(glob.glob(os.path.join(ROOT, "agents", "*.md"))):
        check_agent(f)
    for f in sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))):
        check_skill(f)
    for f in (
        os.path.join(ROOT, ".claude-plugin", "plugin.json"),
        os.path.join(ROOT, ".claude-plugin", "marketplace.json"),
        os.path.join(ROOT, "templates", "settings.snippet.json"),
    ):
        check_json(f)
    for f in sorted(
        glob.glob(os.path.join(ROOT, "docs", "*.md"))
        + glob.glob(os.path.join(ROOT, "templates", "*.md"))
        + [os.path.join(ROOT, "README.md")]
    ):
        check_links(f)

    for p in problems:
        print(p)
    if problems:
        print(f"\n{len(problems)} problem(s).")
        return 1
    print("lint: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
