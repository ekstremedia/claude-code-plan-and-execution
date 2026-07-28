---
title: Gotchas
---

# Gotchas


Things that break this setup silently — where it keeps running and quietly stops
doing what you think it does.

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

