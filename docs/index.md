---
title: claude-code-plan-and-execution
---

# claude-code-plan-and-execution

Plan with an expensive model. Execute with cheap ones. Gate the risky parts.

`/make-plan` researches a problem and writes a self-contained plan file.
`/execute-plan` runs that plan in a fresh session: a cheap orchestrator delegates
every code change to model-pinned workers, reviews the real changes, and routes
high-risk phases through an expensive read-only reviewer.

**[Repository and install instructions →](https://github.com/ekstremedia/claude-code-plan-and-execution)**

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
Session 1 — planning
  /make-plan MyPlan <problem>
      │  model: opus
      ├── planning-researcher   (sonnet, read-only)  ← breadth search
      │                                                 max 2 delegations
      ├── planner reads the decisive files itself
      └── writes plans/MyPlan.md

Session 2 — execution (fresh)
  /execute-plan plans/MyPlan.md
      │  model: sonnet, effort medium
      ├── phase packet ──→ implementer        (sonnet, effort high)
      │                └─→ quick-implementer  (haiku, batched, refuses judgment)
      ├── reads real diff + new untracked files
      ├── Risk: high ────→ plan-reviewer      (opus, read-only, fresh context)
      └── final integration gate over the accumulated change set
```

Every model above is pinned in the agent's own frontmatter. The session model
does not leak into the workers.

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
