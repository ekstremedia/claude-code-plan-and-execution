---
title: Design
---

# Design


## Six roles

The original version of this setup called it five. It listed six.

| Role | Where it lives | Model | Why it exists |
|---|---|---|---|
| **Planner** | `skills/make-plan` | opus (fable when the design is genuinely open) | Synthesis: architecture, phase design, risk, resolving competing approaches |
| **Planning researcher** | `agents/planning-researcher.md` | sonnet | Breadth-first codebase search, so the planner is not paying planner rates to grep |
| **Orchestrator** | `skills/execute-plan` | sonnet | Sequencing, delegating, reviewing, filtering findings |
| **Implementer** | `agents/implementer.md` | sonnet | Writes the code and the tests. Most tokens go here |
| **Quick implementer** | `agents/quick-implementer.md` | haiku | Mechanical, exactly-specified work. Refuses anything else |
| **Reviewer** | `agents/plan-reviewer.md` | opus | Read-only gate at risk points and at the end |

## Why subagents and not skills for the workers

Skills can set `model:` for the turn, and can even fork into a subagent with
`context: fork`. But workers need **isolated context** as much as they need a
model pin: verbose test output, file reads, and failed attempts stay inside the
worker, and only a short report crosses back. Subagents give both. That isolation
is the entire reason a long implementation phase does not swamp the
orchestrator's context.

The corollary is that "report concisely" in the worker prompts is a live
constraint, not boilerplate. If workers write long reports the isolation buys
nothing.

## Why the plan is a file

A plan held in a conversation dies with that conversation, and survives
compaction only by luck. On disk it can be executed in a fresh session that never
loads the planning transcript — cheaper, and cleaner, because the executor sees
requirements instead of the deliberation that produced them.

That only works if the plan is genuinely self-contained, which is what the
[plan-file contract](https://github.com/ekstremedia/claude-code-plan-and-execution/blob/main/templates/PLAN-TEMPLATE.md)
enforces: base commit, goal, success criteria, non-goals, constraints, global
verification commands, and per phase a risk level, verified evidence, required
behaviour, and "done when".

Claude Code's own plan mode also persists to disk now. The `plansDirectory`
setting — *"Custom directory for plan files, relative to project root. If not
set, defaults to `~/.claude/plans/`"* — points it at the repository. Set it to
`plans` and Shift+Tab plan mode writes to the same place `/make-plan` does.
`/make-plan` still earns its keep by controlling the filename, capping research
delegation, and filling the contract.

## The phase packet

The orchestrator does not hand a worker the whole plan, and does not hand it the
phase alone.

Whole plan: the worker re-reads phases 1–4 to implement phase 5, every time.

Phase alone: the worker satisfies the phase and breaks the product, because it
cannot see what the phase is *for*. This is the flaw in the obvious
token-saving advice.

The packet is the middle: overall goal, the success criteria this phase serves,
the phase verbatim, the constraints and non-goals that bind it, dependencies and
deviations from earlier phases, files renamed and APIs changed so far, and the
pre-existing dirty files it must not touch. The orchestrator decides what is
relevant — that is what an orchestrator is for.

## The git discipline

This closes a real hole rather than optimising anything.

`git diff` compares the working tree against the index, so it shows **nothing**
for staged changes and **nothing** for untracked files. An orchestrator told to
"read the actual diff" can therefore approve a phase without ever seeing the new
migration, the new component, or the new test file it added.

So: record `git status --short` before the phase, record it again after, and use
the difference to find every file the phase touched. Review tracked changes with
`git diff HEAD -- <files>`. Read every new untracked file directly. Ignore the
orchestrator's own plan-file status edits. The reviewer gets the same list,
including the untracked files, because it has the same blind spot.

## The final integration gate

Per-phase review is not enough: a phase can pass in isolation while the
combination fails. After the last phase, the orchestrator runs the plan's global
verification commands against the accumulated tree, then one reviewer pass over
the whole change set — including every newly created file — against the goal,
the success criteria, and the non-goals. Findings route back, affected checks
re-run, and only then is it done.

## Coverage lives in the reviewer, filtering lives in the orchestrator

The reviewer reports every plausible finding in its categories, tagged with a
severity and a confidence, and filters nothing. The orchestrator decides what
matters, routes those back, and records in the plan file anything it consciously
declines.

This split exists because a severity filter inside the reviewer reads as an
instruction to withhold, and current models follow it literally: they investigate
just as hard, find the bug, and decline to mention it. Precision goes up,
recall goes down, and real defects vanish silently. See
[Prompting](prompting.md).

The reviewer is also told **not to write the fix** — file, symbol, evidence,
impact, smallest conceptual correction. Two reasons: an expensive model producing
patch text is expensive output for work the cheap model is about to do anyway,
and a pasted patch collapses the role split that makes the review independent.

## Delegate, then commit to the delegation

An orchestrator that re-derives what a subagent already reported pays for the
same work twice at the more expensive tier. The rule is: read the diff to
**verify** the work, not to repeat it. Corrections inside a phase resume the same
implementer (it keeps its context); the next phase gets a fresh one; reviewers
are always fresh.

## When not to use this

A fresh subagent starts cold: no conversation, no prior file reads, no warm
cache. So `orchestrator → implementer → orchestrator reads the diff` can pay
twice to read the same problem. For a three-file feature, one continuous Sonnet
session is often both cheaper and better oriented.

Isolation earns its cost when the implementation produces a lot of output, the
run is long, or the phases are genuinely independent.

| Work | Workflow |
|---|---|
| Small, deterministic edit | Sonnet directly; batched Haiku for mechanical sets |
| Normal feature, clear multi-file bug | Sonnet directly, optionally one closing review |
| Long-running or context-heavy feature | `/make-plan` → `/execute-plan` |
| Migration, auth, security, public API, AI integration | Opus plan → `/execute-plan` → review gates |
| Genuinely open-ended architecture | Fable plan → same execution path |
| Plan turns out to be wrong | Stop, fix the plan with the big model, record the deviation, resume |

A typo, an obvious one-file bug, or a fully specified UI tweak does not need a
plan file at all.

## Stopping a stuck implementer

The tempting control is `maxTurns`. It is the wrong one at small values:
`maxTurns` counts every agentic turn — read the packet, grep, read the service,
read the test, edit, run, read the failure, fix — so a low cap truncates correct
work mid-phase and leaves half-written code behind.

The failure actually worth stopping is *edits that gain no information*. So the
implementer is told: if two materially different repair attempts produce the same
failure and nothing was learned between them, stop and report the failing
command, the hypotheses tested, what changed between attempts, the evidence, and
the most likely next investigation. Three red tests in a row is often just a
correct sequence — the reproduction test failing as designed, then an edge case
surfacing, then a stale fixture.

`maxTurns: 20` is a reasonable backstop if you want a hard limit. Eight is not.

## Effort

`effort` is available on both skills and agents: `low`, `medium`, `high`,
`xhigh`, `max`, or an integer. The top levels are model-gated.

The split that matters is orchestrator versus implementer. Finding the next
phase, assembling a packet, and checking a box do not need the same reasoning
budget as writing the code. So the orchestrator skill runs `medium` and
`implementer` overrides back up to `high`. Without the explicit `effort: high` on
the implementer it would inherit the orchestrator's `medium`.

Agent `effort` is fixed per definition — there is no per-invocation knob. So
"bump the final review to `xhigh`" is not something the orchestrator can do; it
would need a second agent definition. The reviewer stays at `high`, and the final
gate is deepened by telling it in the delegation that this is the whole
accumulated change set against every success criterion.

