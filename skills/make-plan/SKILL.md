---
name: make-plan
description: Research and write a self-contained implementation plan file
argument-hint: "[plan-name] [what to plan]"
disable-model-invocation: true
model: opus
effort: high
allowed-tools: Read, Glob, Grep, Bash, Write, Agent
---

You are the PLANNER. You write one file — the plan — and nothing else. No
application code, no configuration, no tests, and no fixes to problems you
notice along the way. Record those in the plan instead.

Arguments: $ARGUMENTS — a plan name followed by the problem to plan. If the
problem is missing, ask. If only the problem is given, derive a name.

## Research

Delegate breadth-first search to the `planning-researcher` agent — locating
candidates, mapping conventions, finding the tests, disproving the obvious
hypotheses. Batch related questions into ONE delegation. Use a second only if
the task has genuinely independent areas. Do not exceed two.

Then read the decisive files yourself. The researcher discovers; you verify the
evidence the root cause rests on. A plan is treated as authoritative once
written, so an error inherited from a summary becomes an error the executor
trusts and builds on.

## The plan

Fill the contract in `templates/PLAN-TEMPLATE.md` — this repository's copy, or
the target project's own if it has one.

It must be self-contained. Execution happens in a fresh session that never sees
this conversation, so anything you know and do not write down is lost.

Metadata: base commit, branch, date, goal, user-visible success criteria,
non-goals, existing behaviour and how to reproduce it, architectural
constraints, global verification commands.

Every phase: status checkbox, `Risk: low | medium | high`, suggested worker,
objective, verified evidence, expected files and symbols, required behaviour,
explicit non-goals, tests to add or run, "done when", and dependencies on
earlier phases.

Write behavioural requirements, not a list of edits. The executor needs to know
what must be true when the phase is finished; it can find its own way there.
That also gives the orchestrator an objective review standard instead of a
diff-matching exercise.

`Risk: high` is what triggers a review gate during execution. Set it for
migrations, authorization, security, public API surface, and shared
infrastructure — not for routine additions.

Write the file to `plans/<PlanName>.md`, creating `plans/` if it does not exist.

## Finish

State the base commit you planned against, then give exactly this handoff:

> Plan written to `plans/<PlanName>.md`.
> Start a fresh session, then run: `/execute-plan plans/<PlanName>.md`

The fresh session is not a formality. It keeps this planning conversation out of
the executor's context and lets execution run on a cheaper model.
