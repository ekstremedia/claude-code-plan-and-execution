# <Plan name>

## Plan metadata

- **Base commit:**
- **Branch:**
- **Planning date:**
- **Goal:**
- **User-visible success criteria:**
- **Non-goals:**
- **Existing behaviour / how to reproduce:**
- **Relevant architectural constraints:**
- **Global verification command(s):**

<!--
The metadata block is what makes the plan self-contained. Execution runs in a
fresh session that never sees the planning conversation, so anything omitted
here is lost. The base commit lets the orchestrator detect drift before it
starts implementing against a codebase that has moved.
-->

---

## Phase 1 — <name>

- [ ] Status
- **Risk:** low | medium | high
- **Suggested worker:** quick-implementer | implementer
- **Objective:**
- **Verified evidence / root cause:**
- **Expected files and symbols:**
- **Required behaviour:**
- **Explicit non-goals:**
- **Tests or reproduction to add/run:**
- **Done when:**
- **Dependencies from earlier phases:**

---

## Phase 2 — <name>

- [ ] Status
- **Risk:** low | medium | high
- **Suggested worker:** quick-implementer | implementer
- **Objective:**
- **Verified evidence / root cause:**
- **Expected files and symbols:**
- **Required behaviour:**
- **Explicit non-goals:**
- **Tests or reproduction to add/run:**
- **Done when:**
- **Dependencies from earlier phases:**

---

## Deviations and declined findings

<!--
Filled in during execution, not planning. The orchestrator records here what it
changed relative to the plan and which review findings it consciously declined,
so those decisions survive the session instead of being lost in a transcript.
-->

---

## Notes on filling this in

**`Risk: high` is load-bearing.** It is what triggers an Opus review gate during
execution. Set it for migrations, authorization, security, public API surface,
and shared infrastructure. Do not set it for routine additions — a gate on every
phase is a gate on nothing.

**Write required behaviour, not a list of edits.** "Expired sessions must be
rejected with 401 and must not extend the refresh window" survives a refactor;
"add an `if` at `AuthService.php:88`" does not. It also gives the orchestrator an
objective review standard rather than a diff-matching exercise.

**Verified evidence means verified.** Cite `file:line` for what the code
currently does. A plan is treated as authoritative once written; a guess in this
field becomes a guess the executor builds on.

**Global verification commands run once at the end**, against the accumulated
implementation — not per phase. A phase can pass in isolation while the
combination fails.
