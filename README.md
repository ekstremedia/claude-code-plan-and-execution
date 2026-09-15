# claude-code-plan-and-execution

A two-command workflow for Claude Code: **`/make-plan`** researches and writes a
self-contained plan file with an expensive model, **`/execute-plan`** runs that
plan in a fresh session with a cheap orchestrator that delegates every code change
to model-pinned worker agents and gates the risky phases behind an expensive
reviewer.

The point is not saving money. It is that a big model doing grep, running test
suites, and sequencing checkboxes is a big model not doing the thing it is good
at — and a plan that lives only in a conversation dies with that conversation.

Tested against Claude Code **2.1.220**; the transcript tooling and the doctor's
checks re-verified on **2.1.238**. The model-pin drop described below was
measured on **2.1.239**, **2.1.251** and **2.1.259**, and its fix verified
headless on **2.1.272**. Command names and model aliases drift; the structure is
the durable part.

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

Later: `--update` pulls upstream changes in without touching the two adapted
worker agents, and `--uninstall` removes exactly what install placed. After
either, `scripts/doctor.sh /path/to/your/project` asserts the setup is still
wired — every silently-breaking misconfiguration it can check, as PASS/FAIL
lines instead of prose.

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
# new session — set the session model and effort, not just the skill's:
#   /model sonnet  and  /effort medium
#   or start it as: claude --model sonnet --effort medium
/execute-plan plans/RefreshTokens.md
```

The session settings matter because a skill's `model:` and `effort:` frontmatter
applies for the current turn only: from the first subagent-completion
notification onward, the run continues on whatever the session is set to. See
[Four things that break it](#four-things-that-break-it).

Sonnet orchestrates: builds a phase packet, delegates to `implementer`, reads the
real diff plus any new untracked files, sends findings back rather than fixing
them itself, gates `Risk: high` phases through the Opus reviewer, and runs a
final integration check over the accumulated change set. If execution recorded
deviations, it closes with a short retro suggesting which of them belong in
`CLAUDE.md` or a `bin/` wrapper — suggestions only; the user decides.

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
| `scripts/verify-models.py` | Proves from a transcript which model actually ran, and where the tokens went. |  |
| `scripts/doctor.sh` | Asserts an install is wired — the checkable gotchas as PASS/FAIL. |  |

Workers are **subagents**, not skills, because they need isolated context as well
as a model pin: verbose test output and file reads stay inside the worker, and
only a short report crosses back.

---

## Verifying the tiering

The authoritative record of what a skill invocation was pinned to is the
`command_permissions` attachment the harness writes at invocation.
`scripts/verify-models.py` extracts it:

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
  message.model (version-dependent, NOT the pin record): claude-opus-5 x36
```

A skill that declares no `model:` logs no `model` key at all, so the key's
presence is itself the proof the pin was applied. Standard library only, no `jq`.

The `model` field on an assistant message answers a different question, and what
it answers has changed between versions. On 2.1.220–2.1.239 it recorded the
session's configured model throughout — a Fable session logged `claude-fable-5`
for turns a `model: sonnet` skill was executing. On 2.1.259 it recorded the
*effective* model: an Opus session logged `claude-sonnet-5` for the
`/execute-plan` turn, then `claude-opus-5` once the pin dropped. So do not read
it as the pin record on any version; `command_permissions` is that record.

The reliable per-record signal is the top-level **`effort`** field, which is
present on every assistant record and moved in all three runs measured here. The
script watches it, and reports where a pin was lost:

```text
=== a305ab92  /home/terje/projects/huskeapp  2026-09-06T17:20
  skill invocations (command_permissions — authoritative):
    17:20  model=claude-sonnet-5
           allowedTools=<unrestricted>
  delegations: implementer x7, plan-reviewer x1
  task-notifications: 9 (each one starts a new turn)
  WARNING: effort medium→xhigh (model claude-sonnet-5→claude-opus-5) at 17:28
           following a task-notification — the skill pin was dropped; the rest
           of the run ran at the session model/effort
```

That is the 2.1.259 run: `/execute-plan` was invoked in an Opus session, held
`sonnet`/`medium` for its own turn, and ran everything after the first
implementer completion on Opus at `xhigh`. It then cascaded — the now-Opus
orchestrator passed `model: opus` explicitly on all seven `implementer`
delegations, which overrides the agent's own `model: sonnet`, so the worker
transcripts record `claude-opus-5` too.

The same script sums token usage per tier: the main thread from the session
transcript, each worker from its own transcript under `<session>/subagents/`,
grouped by the `agentType` its `.meta.json` records. A real `/execute-plan` run,
measured on 2.1.238:

```text
  tokens (usage records, deduped by message id; out includes thinking):
    main thread            out   39.6k   in     138   cache-read    9.7M   cache-new  258.2k
    implementer x2         out   71.9k   in     284   cache-read     19M   cache-new  548.6k   [claude-sonnet-5]
    plan-reviewer x3       out   54.2k   in     142   cache-read    5.3M   cache-new  289.6k   [claude-opus-5]
    quick-implementer x3   out   22.8k   in     774   cache-read    5.1M   cache-new  200.1k   [claude-haiku-4-5-20251001]
    worker share of output tokens: 79%
```

79% of what the run wrote came out of the workers, on their pinned models. The
bracketed model is read from the worker's own transcript, and there it does
reflect the pin: this session was configured on Sonnet, yet the reviewer's
transcript records `claude-opus-5` and the quick-implementer's records Haiku —
each worker's "session" is its own run, so the configured model *is* the
frontmatter pin. Usage on a streamed message grows across its transcript
records, so the script keeps only the last record per message id — summing them
raw would count most messages several times over.

---

## Four things that break it

**A backgrounded delegation drops the skill's model and effort pin.** Skill
frontmatter applies for the current turn only. Every subagent completion now
arrives as a system-generated notification that starts a *new* turn — on the
session model, at the session effort, with no user input in between. Measured in
three `/execute-plan` runs: the `effort` field on assistant records flips from
the skill's `medium` to the session's `xhigh` at the first notification
(2.1.239, 2.1.251, 2.1.259), and on 2.1.259 `message.model` went
`claude-sonnet-5` → `claude-opus-5` with it, at 17:28:44. The four worker agents
therefore declare `background: false`, which returns each delegation's report as
the tool result and keeps the turn alive — verified headless on 2.1.272, not yet
verified in an interactive session. One-line check for the reader: the
delegation's tool result is the report rather than "Async agent launched
successfully", and `effort` stays at the skill's value across the run.
`scripts/verify-models.py` prints the exact record where it stops.

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

## Composing with other skill packs

This is two skills and four agents, not a skill collection. Where a project also
has one installed — [mattpocock/skills](https://github.com/mattpocock/skills) is
the one this was written against — the two compose without either depending on
the other: `/make-plan` reads `CONTEXT.md` and `docs/adr/` where they exist,
`/execute-plan` names a `tdd` skill in the phase packet where one is installed,
and `plan-reviewer` stays the only reviewer inside the loop. Every reference is
conditional; uninstalling the pack changes nothing here. The reasoning, and the
stage-by-stage map of where the two meet, is on the
[composing page](https://ekstremedia.github.io/claude-code-plan-and-execution/composing).

---

## Documentation

Full rationale, the Opus 5 / Sonnet 5 prompting notes, the `/advisor` question,
and the gotchas list:

**<https://ekstremedia.github.io/claude-code-plan-and-execution/>**

Or read `docs/` in this repository. For agents:
[`llms.txt`](https://ekstremedia.github.io/claude-code-plan-and-execution/llms.txt)
indexes every page and workflow file as raw fetchable markdown.

## License

MIT.
