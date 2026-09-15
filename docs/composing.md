---
title: Composing with other skill packs
description: How this workflow works alongside skill collections it does not depend on — key on the artifacts, not on the pack, and keep one reviewer.
---

# Composing with other skill packs

This workflow is two skills and four agents. It is not a skill collection, and it
deliberately does not become one. Other people ship collections that cover the
parts this one leaves alone — turning a conversation into tickets, test-first
implementation, stress-testing a document, resolving a merge conflict — and a
project usually ends up with both installed.

The question is how the two coexist without either owning the other. The answer
this repository settled on has three rules.

---

## Rule 1 — key on the artifacts, not on the pack

A skill pack is a runtime thing: installed, disabled, upgraded, renamed. The
files it leaves in your repository are not. `CONTEXT.md`, `docs/adr/`,
`docs/agents/issue-tracker.md` sit in git, survive an uninstall, and can be
written by hand by someone who has never installed anything.

So `/make-plan` reads `CONTEXT.md` for vocabulary and `docs/adr/` for decisions
already settled, and continues without comment when neither exists. It never
asks whether a pack is installed. The same instruction works in a repository
that adopted the convention manually, one that installed a different pack with
the same convention, and one that has nothing — three cases, one rule, no
detection.

The failure mode this avoids is the version-pinned path. A plugin's files live
under a directory carrying its version number, so anything referring to that
path breaks on the next upgrade of a package you do not control.

## Rule 2 — soft references, phrased as conditions

Where a genuinely useful skill has no artifact to key on, name it by its bare
name and make the reference conditional:

> Where the project has a test-first skill installed (`tdd` is the usual name)
> and the phase names tests, say so in the packet and let the implementer follow
> it.

An installed `tdd` gets used. An absent one costs the reader one clause. Nothing
errors, nothing is required, and the sentence stays true if you swap packs.

Bare names rather than namespaced ones (`tdd`, not `some-pack:tdd`) because the
same skill arrives under different prefixes depending on how it was installed,
and because a project's own `.claude/skills/tdd/` should satisfy the reference
just as well.

**`/make-plan` cannot invoke a skill at all.** Its `allowed-tools` list is
`Read, Glob, Grep, Bash, Write, Agent` — no `Skill`. That is deliberate: the
planner writes one file and delegates research, and a skill it invoked would
land in the planner's own context at planner rates. So the planner *suggests*;
you run the suggestion. `/execute-plan` withholds only `Write` and
`NotebookEdit`, so it is not under the same restriction.

Whether a **subagent** can reach a skill its parent named is not something this
repository has verified against the binary. Treat the phase packet as the
channel that definitely works: state the convention in the packet text, in
behavioural terms, and the implementer applies it whether or not it can load the
file.

## Rule 3 — one reviewer per change

`/execute-plan` already routes `Risk: high` phases through `plan-reviewer` and
runs a final integration gate over the accumulated change set. A general-purpose
review skill run *inside* that loop is a second strong model doing overlapping
control work on the same diff, and the two disagree at different altitudes: one
against the plan's phase contract, one against the repository's coding
standards.

This is the same reasoning that keeps [the advisor](advisor.md) off during
execution. Both reviews are worth having; they are not worth having
simultaneously on a half-finished tree. Run the broader one after the workflow
reports completion, on the finished change set, where its findings become the
next plan's input rather than mid-flight noise.

---

## Worked example: mattpocock/skills

[mattpocock/skills](https://github.com/mattpocock/skills) is the collection this
page was written against — installable as `mattpocock-skills` from the official
plugin marketplace. It is a useful example because its author documents the same
problem from the other side: his ADR *"Explicit setup pointer only for hard
dependencies"* splits his own skills into ones that break without their config
and ones that merely sharpen with it, and keeps the pointer out of the second
group. Rules 1 and 2 above are that split, applied in the other direction.

Running his `/setup-matt-pocock-skills` once in a repository writes the artifacts
Rule 1 keys on:

| File | Written by | Read by this workflow |
|---|---|---|
| `CONTEXT.md` | `/domain-modeling`, lazily | `/make-plan` — plan vocabulary |
| `docs/adr/` | `/domain-modeling` | `/make-plan` — settled decisions, and conflicts with them |
| `docs/agents/issue-tracker.md` | `/setup-matt-pocock-skills` | `/execute-plan` — where a retro lesson could be filed |
| `docs/agents/domain.md` | `/setup-matt-pocock-skills` | consumer rules for the two above |

Where the two collections meet, by stage:

| Stage | Skill | How it composes |
|---|---|---|
| Before planning | `to-spec`, `to-tickets` | Upstream. A spec or a ticket is the input `/make-plan` plans from. |
| Before planning | `research` | Answers external-documentation questions — library behaviour, API facts — and writes the answer to a file the plan can cite. Different job from `planning-researcher`, which searches *this* codebase and reports back synchronously. |
| After planning | `grilling`, `grill-with-docs` | Interrogates the written plan file before you spend an execution session on it. |
| During execution | `tdd` | Named in the phase packet for phases that specify tests. |
| During execution | `resolving-merge-conflicts` | For a rebase or merge that interrupts a phase. Re-read the phase diff afterwards. |
| After execution | `code-review` | The broader review, on the finished change set. Rule 3. |
| Instead of execution | `implement` | The single-session alternative. When the work is small enough that a plan file and a fresh session are overhead, this is the honest choice — see [when not to use this workflow](design.md). |
| While editing these files | `writing-for-agents` | Reference for editing any skill, including these two. |

Nothing above is a dependency. Uninstall the pack and every sentence in
`skills/` still reads correctly; the conditions simply stop firing.

`docs/agents/` is excluded from this site's build — it is machine configuration
that happens to live under `docs/`, not a page.
