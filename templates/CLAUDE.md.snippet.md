Paste this into the target project's `CLAUDE.md`. Two lines, deliberately.

```markdown
## Saved plans

Saved implementation plans are executed only through the explicitly invoked
`/execute-plan <plan-file>` skill. The orchestration procedure lives in that
skill, not here.
```

---

## Why it is this short

An earlier version of this setup put the whole orchestration procedure in
`CLAUDE.md`. That is the wrong place for it.

`CLAUDE.md` is loaded into **every** session, and custom subagents inherit it
too — so the procedure was being paid for in the planner, the orchestrator,
every implementer, every reviewer, and every unrelated session, while being used
only during an actual plan run.

The skill carries `disable-model-invocation: true`, so its body is not loaded
until you type the command. That is where a procedure used occasionally belongs.
Keep `CLAUDE.md` for invariants that apply to all work in the repository.

## What does belong in CLAUDE.md

The rules an eager agent breaks first, stated once:

- how to run tests (point at the wrappers, not the raw commands)
- navigation, styling, or component conventions that a policy test enforces
- localisation requirements
- files or directories that need extra care

The worker agents inherit all of it. Do not duplicate those rules into the agent
files — at most one or two deliberately repeated lines for whatever footgun bites
hardest in your repository.
