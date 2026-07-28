---
title: claude-code-plan-and-execution
description: Plan with a big model, execute with cheap ones. Two Claude Code commands, four model-pinned agents, and a read-only reviewer gating the risky phases.
---

# claude-code-plan-and-execution

Plan with an expensive model. Execute with cheap ones. Gate the risky parts.

`/make-plan` researches a problem and writes a self-contained plan file.
`/execute-plan` runs that plan in a fresh session: a cheap orchestrator delegates
every code change to model-pinned workers, reviews the real changes, and routes
high-risk phases through an expensive read-only reviewer.

**[Repository and install instructions →](https://github.com/ekstremedia/claude-code-plan-and-execution)**

---

## New to Claude Code?

Claude Code is Anthropic's coding agent. You run it inside a project, describe a
task in plain language, and it reads your files, edits them, runs commands and
tests, and shows you what it changed. It is a terminal program first; there are
also desktop and web apps and IDE extensions.

```bash
curl -fsSL https://claude.ai/install.sh | bash
# or: npm install -g @anthropic-ai/claude-code

cd your-project
claude
```

It needs a Claude subscription or an API key. Official documentation:
[code.claude.com/docs](https://code.claude.com/docs).

Six words the rest of this site assumes:

- **Session** — one conversation, in one directory. Close it and its context is
  gone.
- **Model** — which Claude is doing the work. Bigger models reason better, cost
  more, and are slower. `/model` switches mid-session.
- **Subagent** — a separate Claude with its own context window and its own model,
  spawned to do one job and report a summary back. It never sees the parent
  conversation, so its noise never lands in yours. Defined by a markdown file in
  `.claude/agents/`.
- **Skill** — a reusable instruction file. Typing `/its-name` runs it. Lives at
  `.claude/skills/<name>/SKILL.md`.
- **`CLAUDE.md`** — project rules, loaded into every session automatically.
- **Plan mode** — a read-only mode (Shift+Tab) for settling an approach before
  anything gets edited. `/make-plan` replaces it rather than composing with it;
  run one or the other, never both at once.

### So what is this repository?

Out of the box, one model does everything in one session: the planning, the
grepping, the code, the tests, the review. That works, but it spends your most
capable model on file searches and checkbox-ticking, and the plan it worked out
lives only in that conversation.

This repository is four subagents and two skills that split the work up. An
expensive model plans and writes the plan to a file. A cheap one executes it,
handing each phase to a worker pinned to an appropriate model. An expensive
read-only reviewer checks the parts that can actually hurt you. You install it,
type two commands, and the routing happens without you thinking about it.

It is worth it for long or risky work. For a quick fix it is overhead — the
[design page](design.md) says plainly when not to use it.

---

## Pages

- **[Design](design.md)** — the six roles, why the split, the phase packet, the
  git discipline that closes a real review hole, and when *not* to use any of this.
- **[Prompting](prompting.md)** — what changed with Opus 5 and Sonnet 5, and the
  three prompt consequences. One of them inverts standard prompting advice.
- **[The advisor](advisor.md)** — `/advisor` exists now. What it is, what is
  verified about it, and why it is off inside the orchestrated workflow.
- **[Gotchas](gotchas.md)** — the things that silently break the setup.

---

## The shape in one screen

```
Session 1 — planning        (plan mode OFF — it overrides the skill)
  /make-plan MyPlan <problem>
      │  model: opus
      ├── planning-researcher   (sonnet, read-only)  ← breadth search
      │                                                 max 2 delegations
      ├── planner reads the decisive files itself
      └── writes plans/MyPlan.md

Session 2 — execution (fresh)
  /execute-plan plans/MyPlan.md
      │  model: sonnet, effort medium, Write withheld
      ├── phase packet ──→ implementer        (sonnet, effort high)
      │                └─→ quick-implementer  (haiku, batched, refuses judgment)
      ├── reads real diff + new untracked files
      ├── Risk: high ────→ plan-reviewer      (opus, read-only, fresh context)
      └── final integration gate over the accumulated change set
```

Every model above is pinned in the agent's own frontmatter. The session model
does not leak into the workers.

You can check that from a transcript rather than taking it on trust —
`scripts/verify-models.py` in the repository prints which model each skill
invocation actually ran on. Do not read the `model` field on assistant messages;
it records the session's configured model and will report Opus for an entire run
that executed on Sonnet. [Gotchas](gotchas.md) has the details.

---

## Scope of the claims here

Everything asserted about Claude Code's behaviour was checked against the
shipping binary at version **2.1.220** — frontmatter schemas, settings keys, the
advisor tool, and the plugin loading rules. Where something could not be
verified, the page says so rather than guessing.

Model aliases float: `model: opus` resolves to whatever "opus" currently means,
and that changes under you on a model release. Treat a release as a prompt-review
trigger, not just a changelog entry — [Prompting](prompting.md) explains why that
matters more than it sounds.
