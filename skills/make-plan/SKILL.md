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

## Preflight

State the model you are running as. If it is not Opus, say so — the tiering
assumes an expensive planner, and the user may want to restart.

Then check whether **plan mode is active**. Signs: a plan-mode system message, a
harness-supplied plan file path (typically under `~/.claude/plans/`), a "Plan
Workflow" you did not ask for, or a fence naming one file as the only one you may
edit. The `$ARGUMENTS` plan name is not such a sign.

If it is, **stop**. Do not research, do not delegate, do not write. Say:

> Plan mode is active, and its built-in workflow overrides this skill — it
> forces Explore-only research and confines writes to `~/.claude/plans/`. Leave
> plan mode with Shift+Tab, then run `/make-plan` again.

This is not a formality. It has happened in practice: the plan landed outside the
repository and every research delegation went to `Explore` at planner rates.
`/make-plan` replaces plan mode; the two do not compose.

## Research

Delegate breadth-first search to the **`planning-researcher`** agent — locating
candidates, mapping conventions, finding the tests, disproving the obvious
hypotheses. Under a plugin install it appears as
`plan-and-execute:planning-researcher`; either name is the same agent.

Do **not** use `Explore`, `general-purpose`, or any other search agent for this.
They inherit the session model, so breadth-first grepping would run at planner
rates — which is the entire cost the researcher tier exists to avoid.

Scope the delegations to the work, not to a fixed number. **One delegation per
genuinely independent area; batch every question about an area into that one
delegation.** Areas are independent when neither one's answer changes where you
would look for the other's — separate repositories, unrelated subsystems,
unrelated bugs that happen to arrive in the same request.

Most tasks have one area, so most tasks get one delegation. A five-bug report
spanning a mobile client and its backend does not; forcing that into a single
delegation produces one long serial search and a report that has to cover
everything at once.

Do not split what shares evidence. Two questions answered by reading the same
files are one delegation — splitting them pays for the same search twice and
gives you two half-views to reconcile.

Dispatch independent delegations **in parallel, in a single message**, and
**synchronously** — `run_in_background: false`. Subagents run in the background
by default, which is wrong here: you cannot write the plan before the evidence
arrives, and a researcher whose report lands after you have given up and started
grepping yourself has been paid for and discarded.

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
That path is canonical and it is the only copy. Do not also write to
`~/.claude/plans/`, and do not leave a second copy behind anywhere.

## Finish

State the base commit you planned against, then give exactly this handoff:

> Plan written to `plans/<PlanName>.md`.
> Start a fresh session, then run: `/execute-plan plans/<PlanName>.md`

The fresh session is not a formality. It keeps this planning conversation out of
the executor's context and lets execution run on a cheaper model.
