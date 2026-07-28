---
title: Prompting
---

# Prompting the current models

[← index](index.md)

A model release is a prompt-review trigger, not just a changelog entry. `model:
opus` in agent frontmatter silently resolves to whatever "opus" means today —
so a prompt tuned against the previous model rides along and can quietly get
worse.

Two of Opus 5's behavioural shifts run *opposite* to Opus 4.8, which is what
makes them easy to miss: the instructions written to correct 4.8 now push in the
wrong direction.

| Behaviour | Opus 4.8 | Opus 5 | What to do |
|---|---|---|---|
| Subagent delegation | Under-reached; needed nudging | Reaches freely | Delete "use subagents" nudges. Cap spawn counts explicitly instead |
| Self-verification | Had to be told to verify | Verifies unasked | **Delete** "double-check your work". Removing it cuts over-verification with no loss of rigour |
| Task scope | Stayed put | Can widen the task, or apply its own judgment about what the task *should* be, without saying so | Keep explicit scope fences. They carry real weight now |
| Response length | — | Longer prose, and longer files written to disk | Ask for concision in words. Lowering `effort` moves thinking, not prose |
| Self-correction | — | Narrates its own earlier mistakes at length | Scope corrections to the ones that change what the reader does next |

## Three consequences, concretely

**1. A severity filter in a reviewer is now a bug.**

"Report only material findings" and "skip subjective style preferences" read as
instructions to *withhold*. The model obeys literally: it investigates just as
thoroughly, finds the defect, and then declines to report it as below the bar.
Precision rises, recall falls, and real bugs disappear without a trace.

The fix is to move the filter. The reviewer reports every plausible finding in
named categories with a severity and a confidence; the orchestrator filters. That
filtering step already existed in the loop — it just was not being used as the
filter.

Note the shape of the instruction: it is not "report absolutely everything",
which invites aesthetic noise. It is *report everything within these categories,
never omit for low severity or confidence, exclude pure aesthetics unless they
break a stated rule, and consolidate same-root-cause findings.* High recall
without paying for taste.

**2. "Don't fix it yourself" needs a sibling.**

An Opus orchestrator delegates readily — that is the role working as intended —
but is also prone to re-deriving what the subagent already reported, paying twice
at the expensive tier. So: *if you delegate, commit to the delegation. Read the
diff to verify the work, not to repeat it.*

**3. "Report concisely" is load-bearing.**

Both Opus 5 and Sonnet 5 default to longer output than their predecessors, and
the entire value of subagent isolation is that only a short report crosses back.
Treat the concision instruction in the worker prompts as a live constraint, not
boilerplate.

## Effort

Opus 5 supports `low` through `max`. Start at `high` for review gates and sweep
*down* — `low` and `medium` are unusually strong on this model, and an effort
level inherited from a previous model is rarely the right one. `max` can
overthink; do not reach for it reflexively.

## Sonnet 5 in the worker seats

- It follows instructions **more literally**. Holdover directives now apply at
  face value — re-read them rather than assuming they are inert.
- It is more agentic: it reaches for tools and verifies on its own.
- It gives better in-progress updates by default, so any "summarise progress
  every N steps" scaffolding can go.
- Its `effort` defaults to `high`, and `medium` is a real cost lever for the
  orchestrator tier. This setup uses `medium` for orchestration and `high` for
  implementation.

## Tokenization

Newer models produce meaningfully more tokens for the same text than older ones
— roughly a third more is the figure quoted for the current generation, but the
exact difference depends on the content. A cost or context baseline measured on
an older model under-predicts. Measure rather than extrapolate, and do not treat
a mixed-generation fleet as directly comparable per token.

[← index](index.md)
