---
title: The advisor
---

# The advisor


Claude Code has an experimental **advisor**: a stronger model the running model
can consult mid-task. This page exists because an earlier version of these notes
confidently stated that no such feature existed. It does.

## What is verified

Checked directly against the Claude Code 2.1.220 binary:

- A tool named `AdvisorTool`, described to the model as *"an `advisor` tool
  backed by a stronger reviewer model. It takes NO parameters — when you call
  `advisor()`, your entire conversation history is automatically forwarded."*
- Settings key **`advisorModel`** — *"Advisor model for the server-side advisor
  tool."*
- A **`--advisor`** launch flag, and a **`/advisor`** command: an error path in
  the binary reads *"run /advisor to change or disable the advisor"*.
- Environment switches `CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL` and
  `CLAUDE_CODE_DISABLE_ADVISOR_TOOL`.
- A capability gate. The binary refuses with *"(advisor must be at least as
  capable as the base model)"* and, for unrecognised models, *"has no advisor
  rank in the model catalog. Switch to a public model alias (opus, sonnet,
  fable)"*. So a Sonnet session can consult Opus; the reverse is rejected.
- It is **server-side**, and it decides nothing on its own: the model chooses
  when to call it. The instructions it is given tell it to call before committing
  to an approach, when stuck, when changing approach, and before declaring the
  task complete.

## What is not verified

**Whether advisor configuration propagates into subagents.** It is plausible and
it has been claimed, but nothing in the binary confirmed it either way, so this
page will not assert it. If it does propagate, a saved `advisorModel: opus`
means your Sonnet orchestrator *and* every Sonnet implementer may start
consulting Opus, and the cost profile stops matching what the workflow implies.

Check it yourself before relying on either answer: enable an advisor, run a plan
phase, and watch whether advisor calls appear inside the subagents.

## Why it is off inside `/execute-plan`

Two strong models doing overlapping control work.

This workflow already has deterministic Opus review: at `Risk: high` phases and
once over the accumulated change set, with fresh context and an explicit scope.
An always-available advisor adds a second expensive reviewer that fires at
model-chosen moments, with the whole conversation attached, and no hard cap on
how often.

The explicit gate is the better instrument *here* because it is predictable, it
starts clean instead of inheriting the orchestrator's framing, and it is aimed at
a defined change set.

So the orchestrator skill says to keep the advisor off in this mode. If you have
one saved globally:

```
/advisor          # inspect / change / disable for this session
```

## Where the advisor is the better tool

The lightweight mode. One continuous Sonnet session writing the code directly,
with an Opus advisor available when it gets stuck or is about to commit to an
approach. No plan file, no orchestrator, no phase packets — and none of the
double-reading that a delegated pipeline pays for on a small task.

That is the right shape for a normal feature or an ordinary multi-file bug. Reach
for the orchestrated workflow when the task is long, context-heavy, or genuinely
risky. The two are alternatives, not layers.

