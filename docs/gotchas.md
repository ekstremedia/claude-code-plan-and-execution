---
title: Gotchas
description: The things that silently break a model-tiered Claude Code setup — and keep running while they do it.
---

# Gotchas


Things that break this setup silently — where it keeps running and quietly stops
doing what you think it does.

## Do not run `/make-plan` from plan mode

Plan mode injects its own workflow into the session, and that injection outranks
a skill body. Two things follow, both observed in a real run:

- *"In this phase you should only use the Explore subagent type"* — so every
  research delegation goes to `Explore`, which inherits the session model. The
  cheap researcher tier is bypassed and breadth-first grepping runs at planner
  rates.
- *"this is the only file you are allowed to edit"*, pointing at the harness's
  own plan path. The plan lands in `~/.claude/plans/<auto-slug>.md` instead of
  `plans/<PlanName>.md`, outside version control, usually followed by a copy —
  so now there are two.

The symptom is a plan in the wrong directory and no `planning-researcher`
anywhere in the agent list. Hardening the skill's wording does not fix it; the
skill never had the last word. `/make-plan` therefore checks for plan mode and
refuses, and `plansDirectory` is worth setting so that even the plan-mode path
stays inside the repository.

## `message.model` in a transcript is not the effective model

Every assistant turn in a session `.jsonl` records the *session's* configured
model, not the one that ran the turn. A `/execute-plan` run measured here logged
`claude-opus-5` on all 521 main-thread turns while the skill was executing on
Sonnet. Reading that field will tell you the tiering is broken when it is fine.

The authoritative record is the `command_permissions` attachment emitted when a
skill is invoked:

```json
{"type": "command_permissions", "allowedTools": ["Read","Glob","Grep","Bash","Write","Agent"], "model": "claude-opus-5"}
{"type": "command_permissions", "allowedTools": [], "model": "claude-sonnet-5"}
```

A skill with no `model:` pin logs **no `model` key at all** — so the key's
presence is itself the signal that frontmatter was applied.
[`scripts/verify-models.py`](https://github.com/ekstremedia/claude-code-plan-and-execution/blob/main/scripts/verify-models.py)
pulls this out of a transcript for you.

## `CLAUDE_CODE_SUBAGENT_MODEL` overrides every `model:` pin

It takes first precedence over agent frontmatter. Set it to Sonnet "for
consistency" and you have silently overridden the Haiku `quick-implementer` and
the Opus `plan-reviewer` — the tiering is gone and nothing tells you. Do not set
it. Frontmatter pins are targeted and sufficient.

Managed settings can do the same thing through `availableModels` and
`modelOverrides`, which remap aliases at the policy level.

## Plugin agents drop `permissionMode`, `hooks`, and `mcpServers`

Claude Code says so directly: *"sets `<field>`, which is ignored for plugin
agents. Use `.claude/agents/` for this level of control."*

`planning-researcher` and `plan-reviewer` use `permissionMode: plan` to be
*unable* to write. Installed via the plugin they are only *instructed* not to.
If that distinction matters, use `install.sh`.

## Do not run both distribution paths at once

Plugin agents are namespaced — `plan-and-execute:planning-researcher` — so they
do **not** shadow a project's `.claude/agents/planning-researcher.md`. Both load,
under different names, and the orchestrator picks one. Measured here: it picked
the plugin copy, the one that had lost `permissionMode: plan`, while the enforced
project copy sat unused. The read-only guarantee degraded to prompt-only and
nothing said so.

Pick one path per project. If projects are installed with `install.sh`, leave the
plugin disabled in `~/.claude/settings.json`.

## A directory-source plugin is a snapshot, not a live link

`/plugin marketplace add /path/to/repo` copies the tree into
`~/.claude/plugins/cache/` at install time. Editing the repo afterwards changes
nothing that Claude Code loads, and the cache stays pinned to the installed
version string — so bumping only file contents, without bumping `version` in
`plugin.json`, gives you no way to tell a stale install from a fresh one. Develop
against `install.sh`; use the plugin to test the packaged path.

## Built-in Plan and Explore skip `CLAUDE.md`

And built-in Plan inherits the main-session model — so in a planning session it
runs your expensive planner to do grep work. That is why
`planning-researcher` exists: it is pinned to Sonnet regardless of the session
model, and, being a custom agent, it does inherit `CLAUDE.md`.

## Auto-delegation not happening? It is the `description`

Almost always. Start it with "Use this agent to…" and include "use proactively".
The `description` is what the orchestrator matches against; the body is only read
after the agent is chosen.

## Model aliases float

`model: opus` became a different model on a release, with the same config and no
warning. Capability went up; behaviour moved too, and a prompt tuned to the
previous model can get quietly worse — see [Prompting](prompting.md) for the
severity-filter case, which is exactly this.

Pin a full model ID only if you actually want frozen behaviour. You then own the
upgrade manually, and you lose portability: aliases resolve differently across
providers, and on some setups `sonnet` still points at an older generation. You
cannot have both provider portability and a guaranteed model version — pick one
deliberately.

## `plansDirectory` must be inside the project root

*"Custom directory for plan files, relative to project root. If not set, defaults
to `~/.claude/plans/`."* An absolute path outside the repository is rejected.

## Subagent resume is real, and reviewers must not use it

A parent session can continue a completed subagent by messaging its agent id; the
subagent keeps its full prior context. Use it for corrections inside the current
phase — the implementer already knows what it did. Never for a reviewer: the
value of a review is the fresh context, and a resumed reviewer is reviewing its
own framing.

## `effort` is fixed per agent definition

There is no per-invocation effort knob. "Bump the final review to `xhigh`" is not
something the orchestrator can do — it would need a second agent definition. If
you want a deeper final gate, either add one, or deepen it in the delegation
prompt by naming the scope: the whole accumulated change set, every success
criterion.

## `opusplan` is the built-in near-equivalent

The built-in `opusplan` mode has the big model plan and a cheaper one execute,
which approximates sessions 1 and 2 for medium-complexity work in one command.
The manual split still wins when you want the plan **on disk**: `opusplan` keeps
it in context, so it dies with the session.

## Fast mode buys latency, not intelligence

`/fast` on Opus is real Opus with faster output, not a downgrade to a smaller
model — but it is priced as a premium. Worth it for an orchestrator you are
watching; wasteful for a background review gate.

## Duplication budget

`CLAUDE.md` holds universal invariants. Agent files hold the role contract plus
at most the one or two rules that bite that role hardest. The skill holds the
orchestration procedure.

Repeating a long pinned test command in both worker agents is a symptom, not a
solution — put it behind a `bin/test-<lang>` wrapper and the duplication shrinks
to one line everywhere. See
[`templates/bin/test-example.sh`](https://github.com/ekstremedia/claude-code-plan-and-execution/blob/main/templates/bin/test-example.sh).

