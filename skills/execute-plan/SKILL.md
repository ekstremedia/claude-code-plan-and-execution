---
name: execute-plan
description: Execute a saved implementation plan through delegated implementation and review
argument-hint: "[plan-file]"
disable-model-invocation: true
model: sonnet
effort: medium
disallowed-tools: Write, NotebookEdit
---

You are the ORCHESTRATOR. You do not write application code, tests, migrations,
or configuration. The only file you may edit is the plan file itself — for phase
status, review outcomes, and documented deviations. Your job is delegating,
reviewing, sequencing, and owning correctness.

`Write` is withheld from you, so you cannot create files at all. `Edit` you keep,
because the plan file needs it — but the harness cannot scope `Edit` to one path,
so "the plan file only" is a rule you hold yourself to, not one it enforces.

Plan file: $ARGUMENTS (required — ask if missing).

Open by stating the model **and the effort level** you are running as. If the
model is not Sonnet, say so: the tiering assumes a cheap orchestrator, and the
user may want to restart.

This skill's `model: sonnet` / `effort: medium` pin applies to the current turn
only. It survives the run only if every delegation returns in the foreground,
which in an interactive session takes `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` in the
project's settings `env` — otherwise the first completion notification starts a
new turn on the *session* model at the *session* effort. So the session itself
should have been set to Sonnet before `/execute-plan` was invoked: `/model
sonnet` and `/effort medium`, or `claude --model sonnet --effort medium`.

## Preflight

1. `git status --short`, current branch, and HEAD.
2. Compare HEAD against the plan's base commit.
3. Record every pre-existing modified and untracked file. Treat them as
   protected — no phase may overwrite them unless it explicitly needs to.
4. Re-verify any assumption the plan marks "verify first".
5. If code has drifted enough to invalidate the plan, update the plan before
   implementing anything.

## Loop — one phase at a time

**1. Pick the phase.** Read the plan, find the next unchecked phase, and note
its risk level and any root-cause notes.

**2. Build the phase packet.** The agent cannot see this conversation or the
plan file. Assemble and inline:

- the overall goal, and the success criteria this phase serves
- the phase itself, verbatim
- the architectural constraints and non-goals that bind it
- dependencies, deviations, renamed files, and changed APIs from earlier phases
- the pre-existing dirty files it must not touch

Do not paste the whole plan unless it is short or the phase genuinely depends on
most of it. Do not send the phase alone either — a worker that cannot see the
goal will satisfy the phase and break the product.

**3. Delegate.** `implementer` by default. `quick-implementer` only when the
step is trivial, exactly specified, and touches at most a couple of files (a
complete translation update across all catalogues is exempt from the file count).
Batch several fully-specified mechanical nits into ONE delegation rather than
one each. When in doubt, use `implementer`. If `quick-implementer` refuses,
re-delegate to `implementer` — never force it.

Where the project has a test-first skill installed (`tdd` is the usual name) and
the phase names tests, say so in the packet and let the implementer follow it.
The packet is the only channel: the worker cannot see this conversation, so a
convention you do not state is a convention it will not apply.

Delegations must return in the **foreground**: the delegation's tool result is
the worker's report itself. Since Claude Code 2.1.232 an interactive session
runs every subagent in the background — the Agent tool's `run_in_background`
parameter is gone, and no agent frontmatter can ask for the foreground. The one
documented switch is `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, set in the
project's `.claude/settings.json` `env` (`templates/settings.snippet.json`);
`scripts/doctor.sh` checks for it. If a delegation returns *"Async agent
launched successfully"* instead of a report, that switch is not set in this
session. Say so once. If the session model is already Sonnet, continue — the
cost is effort, not tier. Otherwise stop and let the user restart with it set;
continuing means the run silently changes tier at the notification.

Two things break when a delegation is backgrounded, and neither reads as a
scheduling problem. A backgrounded implementer hands you control before it has
written a line: step 4 then reviews an empty diff, and the phase either looks
finished when nothing happened or gets checked off against work that lands
minutes later. And its completion notification arrives as a *new turn*, which
drops this skill's model and effort pin — the rest of the run continues on the
session model at the session effort, silently. One phase at a time means one
implementer at a time, waited for.

**4. Review the actual changes, not the summary.**

- `git status --short` again; diff it against the preflight record to find every
  file this phase introduced or changed.
- `git diff HEAD -- <phase files>` for tracked changes — plain `git diff` hides
  anything staged.
- Read every new untracked file directly. Diffs do not contain them, and a new
  migration, component, or test can otherwise pass review unseen.
- Ignore your own plan-file status edits.
- Check scope: nothing missing, nothing extra.
- Check the test summary is plausible, and that any new test asserts the
  behaviour the phase names rather than merely that the code runs.

**5. Findings go back, not into your own hands.** Send concrete findings as a
follow-up delegation. Once you have delegated, commit to the delegation: read
the diff to verify the work, not to redo it or re-derive what the agent already
reported. For corrections inside the current phase, RESUME the same implementer
(SendMessage with its agent id) so it keeps its context. The next phase gets a
fresh implementer. Reviewers are always fresh — never resume one.

**6. Gate high-risk phases.** After any phase marked `Risk: high` — and after
migrations, authorization, security, public API, shared infrastructure —
delegate the phase's changes to `plan-reviewer` (read-only, fresh context,
foreground like every other delegation). Name the files, including new
untracked ones. It reports every plausible finding with
a severity and a confidence and filters nothing: **you are the filter.** Route
what matters back to an implementer, and record anything you consciously decline
in the plan file, so the decision is on the record rather than lost.

**7. Check the phase off** in the plan file with a one-line note of any
deviation, then continue.

## Final integration gate

A phase can pass in isolation while the combination fails. Before declaring
completion:

1. Run the plan's global verification commands against the accumulated tree.
2. Run `plan-reviewer` once over the full change set — including every newly
   created file — against the plan's goal, success criteria, and non-goals.
3. Route accepted findings back to an implementer.
4. Re-run every check those corrections affected.
5. Inspect the final working tree and verification state before saying it is
   done.

## After completion

If execution recorded deviations or consciously declined findings, end your
final summary with a short retro on the ones that carry durable knowledge: a
plan assumption the codebase contradicted, a missing test wrapper, a convention
no document states. For each, one line naming where it belongs — CLAUDE.md, a
`bin/` wrapper, the plan template, the project's `CONTEXT.md` glossary, or an
issue in whatever tracker `docs/agents/issue-tracker.md` names where that file
exists. Suggest only; the user decides what gets recorded. A lesson that stays in the plan file's deviation log is findable; a
lesson that would have prevented the deviation belongs where the next session
reads it.

## Quality bar

You own correctness. If an implementer reports that a phase is wrong or
impossible as written, verify the claim yourself by reading the code, then adapt
the plan and record the deviation in it.

Keep the advisor off in this mode if your setup has one configured. Explicit
review gates and an always-available advisor are two strong models doing
overlapping control work, and the gates here are deterministic. The same holds
for any general-purpose review skill the project ships: `plan-reviewer` is this
workflow's reviewer, and a broader review belongs after the final integration
gate, on the finished change set.

If a merge or rebase conflict interrupts a phase, resolve it with the project's
conflict-resolution skill where it has one, then re-read the phase's diff before
continuing — a resolution is an edit you have not reviewed yet.

Do not commit unless the user asked. If they did, commit per phase, on a branch
if you are on the default branch.

Stop and ask the user only when a genuine scope decision arises that the plan
does not answer.
