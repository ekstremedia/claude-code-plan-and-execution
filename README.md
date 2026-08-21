# claude-code-plan-and-execution

A two-command workflow for Claude Code: **`/make-plan`** researches and writes a
self-contained plan file with an expensive model, **`/execute-plan`** runs that
plan in a fresh session with a cheap orchestrator that delegates every code change
to model-pinned worker agents and gates the risky phases behind an expensive
reviewer.

The point is not saving money. It is that a big model doing grep, running test
suites, and sequencing checkboxes is a big model not doing the thing it is good
at — and a plan that lives only in a conversation dies with that conversation.

Tested against Claude Code **2.1.220**. Command names and model aliases drift;
the structure is the durable part.

---

## Install

**As a plugin** — one line, but see the caveat below:

```
/plugin marketplace add ekstremedia/claude-code-plan-and-execution
/plugin install plan-and-execute
```

Commands become `/plan-and-execute:make-plan` and `/plan-and-execute:execute-plan`.

**Into a project** — copies the files into `.claude/`, where you can edit them:

```bash
git clone https://github.com/ekstremedia/claude-code-plan-and-execution
./claude-code-plan-and-execution/install.sh /path/to/your/project
```

> **The plugin path is the weaker of the two.** Claude Code ignores
> `permissionMode`, `hooks`, and `mcpServers` in plugin-packaged agents. The two
> read-only agents — `planning-researcher` and `plan-reviewer` — rely on
> `permissionMode: plan` to be *unable* to write. Installed as a plugin they are
> only instructed not to write. Use `install.sh` if that distinction matters to
> you.

**Pick one path per project.** Plugin agents are namespaced
(`plan-and-execute:plan-reviewer`), so they do not shadow a project's own copies
— both load under different names, and the orchestrator may reach for the
unenforced one. If a project is installed with `install.sh`, keep the plugin
disabled there.

Then adapt the two worker agents: both carry a `<!-- PROJECT: -->` marker naming
what to replace.

---

## Use

```
/make-plan RefreshTokens fix sessions surviving password change
```

Opus researches (via a cheap read-only researcher), verifies the decisive
evidence itself, and writes `plans/RefreshTokens.md` — metadata, phases, risk
levels, acceptance criteria. It ends by telling you the next command.

Run it with **plan mode off**. Plan mode injects its own workflow, which outranks
the skill: research gets forced onto `Explore` at planner rates and the plan is
written outside the repository. `/make-plan` replaces plan mode rather than
composing with it, and refuses to run inside it.

```
# new session
/execute-plan plans/RefreshTokens.md
```

Sonnet orchestrates: builds a phase packet, delegates to `implementer`, reads the
real diff plus any new untracked files, sends findings back rather than fixing
them itself, gates `Risk: high` phases through the Opus reviewer, and runs a
final integration check over the accumulated change set.

Steering mid-run works normally — *"redo phase 3, the overlay change missed the
trip filter"* is picked up as a follow-up delegation.

---

## When to use it

The full workflow is not the default for every task. A fresh subagent starts with
cold context, so orchestrator → implementer → orchestrator-reads-the-diff can pay
twice to read the same problem. Isolation earns its cost when output is
voluminous, the run is long, or the phases are independent.

| Work | Workflow |
|---|---|
| Small, deterministic edit | Sonnet directly; batched Haiku for mechanical sets |
| Normal feature, clear multi-file bug | Sonnet directly, optionally one closing review |
| Long-running or context-heavy feature | `/make-plan` → `/execute-plan` |
| Migration, auth, security, public API, AI integration | Opus plan → `/execute-plan` → review gates |
| Genuinely open-ended architecture | Fable plan → same execution path |
| Plan turns out to be wrong | Stop, fix the plan with the big model, record the deviation, resume |

---

## What is in here

| Path | Role | Model |
|---|---|---|
| `skills/make-plan/` | Planner. Research budget, plan-file contract, handoff. | `opus` |
| `skills/execute-plan/` | Orchestrator. Delegates, reviews, gates, integrates. | `sonnet` |
| `agents/planning-researcher.md` | Read-only breadth search during planning. | `sonnet` |
| `agents/implementer.md` | Writes the code and the tests, one phase at a time. | `sonnet` |
| `agents/quick-implementer.md` | Mechanical, exactly-specified work. Refuses judgment. | `haiku` |
| `agents/plan-reviewer.md` | Read-only risk gate over the real changes. | `opus` |
| `templates/PLAN-TEMPLATE.md` | The plan-file contract. |  |
| `templates/CLAUDE.md.snippet.md` | Two lines to paste into the project. |  |
| `templates/settings.snippet.json` | `plansDirectory`, permissions. |  |
| `templates/bin/test-example.sh` | The test-wrapper convention. |  |
| `scripts/verify-models.py` | Proves from a transcript which model actually ran. |  |

Workers are **subagents**, not skills, because they need isolated context as well
as a model pin: verbose test output and file reads stay inside the worker, and
only a short report crosses back.

---

## Verifying the tiering

Do not check the `model` field on assistant messages in a session transcript — it
records the session's configured model, not the one that ran the turn. It will
report `opus` for an entire `/execute-plan` run that executed on Sonnet.

The authoritative record is the `command_permissions` attachment written when a
skill is invoked. `scripts/verify-models.py` extracts it:

```bash
python3 scripts/verify-models.py                 # sweep ~/.claude/projects/
python3 scripts/verify-models.py SESSION.jsonl   # one transcript
```

```
=== 53df59da  /home/terje/projects/huskeapp  2026-07-28T11:59
  skill invocations (command_permissions — authoritative):
    12:02  model=claude-opus-5
           allowedTools=Read, Glob, Grep, Bash, Write, Agent
  delegations: Explore x3
  WARNING: Explore x3 inherits the session model — a research delegation here
           bypasses planning-researcher and runs at planner rates
  message.model (session config, NOT effective): claude-opus-5 x36
```

A skill that declares no `model:` logs no `model` key at all, so the key's
presence is itself the proof the pin was applied. Standard library only, no `jq`.

---

## Three things that break it

**`CLAUDE_CODE_SUBAGENT_MODEL`** takes precedence over every agent's `model:`
frontmatter. Setting it collapses the whole tiering onto one model, silently.
Do not set it.

**A long `CLAUDE.md` orchestration block.** `CLAUDE.md` is loaded in every session
*and* inherited by every custom subagent. The procedure belongs in the skill,
which is not loaded until you invoke it. `templates/CLAUDE.md.snippet.md` is two
lines for exactly this reason.

**Raw test commands in agent prompts.** Put them behind `bin/test-<lang>`
wrappers that require an explicit target, pin the environment, preserve the exit
code, and print a summary instead of the full log. This shortens both worker
prompts, removes command drift, and keeps test output out of context. See
`templates/bin/test-example.sh`.

---

## Documentation

Full rationale, the Opus 5 / Sonnet 5 prompting notes, the `/advisor` question,
and the gotchas list:

**<https://ekstremedia.github.io/claude-code-plan-and-execution/>**

Or read `docs/` in this repository.

## License

MIT.
