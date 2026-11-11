#!/usr/bin/env bash
#
# Assert that a plan-and-execute install is actually wired — the checkable
# gotchas as assertions instead of prose.
#
#   scripts/doctor.sh /path/to/project            check an installed project
#   scripts/doctor.sh /path/to/project --probe    also RUN the bin/ wrappers
#                                                 with no argument and an empty
#                                                 argument, expecting a refusal
#
# Without --probe the wrapper check is static (present, executable). --probe
# executes them; a conforming wrapper refuses in milliseconds, but a broken one
# may start the full suite — run it when that is acceptable.
#
# Exit code: 0 if no FAIL (warnings allowed), 1 otherwise.
# Needs python3 for JSON; no jq.

set -uo pipefail
export LC_ALL=C

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TARGET=""
PROBE=0
for arg in "$@"; do
  case "$arg" in
    --probe) PROBE=1 ;;
    -h|--help)
      sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    -*) echo "unknown option: $arg" >&2; exit 2 ;;
    *)
      if [[ -n "$TARGET" ]]; then echo "more than one target given" >&2; exit 2; fi
      TARGET="$arg" ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "usage: $(basename "$0") <project-dir> [--probe]" >&2
  exit 2
fi
if [[ ! -d "$TARGET" ]]; then
  echo "not a directory: $TARGET" >&2
  exit 1
fi
TARGET="$(cd "$TARGET" && pwd)"

npass=0; nwarn=0; nfail=0
pass() { echo "  PASS  $*"; npass=$((npass + 1)); }
warn() { echo "  WARN  $*"; nwarn=$((nwarn + 1)); }
fail() { echo "  FAIL  $*"; nfail=$((nfail + 1)); }
info() { echo "  info  $*"; }

# jget <file> <python-expression over d> — prints the value, empty for
# null/missing, __ERR__ if the file is not valid JSON.
jget() {
  python3 - "$1" "$2" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("__ERR__"); raise SystemExit
try:
    # The expression is a literal from this script, not user input.
    v = eval(sys.argv[2], {"d": d})
except Exception:
    v = None
print("" if v in (None, False) else v)
PY
}

# frontmatter <file> — the lines between the first two `---` fences.
frontmatter() {
  awk '/^---[[:space:]]*$/ { n++; next } n == 1 { print } n >= 2 { exit }' "$1"
}

# The installed Claude Code version, empty if `claude` is not on PATH. Several
# checks below depend on it: behaviour this workflow leans on changed between
# versions.
CC_VERSION=""
if command -v claude >/dev/null 2>&1; then
  CC_VERSION="$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
fi

# version_lt <a> <b> — true if dotted version a sorts before b.
version_lt() {
  [[ "$1" != "$2" ]] && [[ "$(printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n | head -1)" == "$1" ]]
}

# Managed (policy) settings live outside the home directory, per platform.
case "$(uname -s 2>/dev/null)" in
  Darwin) MANAGED="/Library/Application Support/ClaudeCode/managed-settings.json" ;;
  *)      MANAGED="/etc/claude-code/managed-settings.json" ;;
esac

READONLY_AGENTS="planning-researcher plan-reviewer"
WORKER_AGENTS="implementer quick-implementer"
ALL_AGENTS="$READONLY_AGENTS $WORKER_AGENTS"
SKILLS="make-plan execute-plan"

echo "doctor: $TARGET"
echo "        (source repo: $SRC)"
echo

# ── 1. Subagent model overrides ──────────────────────────────────────────────
# Claude Code resolves a subagent's model in this order: the delegation's own
# `model` argument, the agent's `model:` frontmatter, CLAUDE_CODE_SUBAGENT_MODEL,
# the session model. So that variable is only a default for unpinned agents —
# since 2.1.251. Before that it came first and overrode every pin. What
# collapses the tiering now is CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1 (2.1.257+):
# with it on, every agent's `model:` is ignored.

force_at=""
model_at=""
[[ "${CLAUDE_CODE_SUBAGENT_MODEL_FORCE:-}" == "1" ]] && force_at="the environment"
[[ -n "${CLAUDE_CODE_SUBAGENT_MODEL:-}" ]] && model_at="the environment (=$CLAUDE_CODE_SUBAGENT_MODEL)"

for f in "$TARGET/.claude/settings.json" "$TARGET/.claude/settings.local.json" \
         "$HOME/.claude/settings.json" "$MANAGED"; do
  [[ -f "$f" && -r "$f" ]] || continue
  v="$(jget "$f" 'd.get("env", {}).get("CLAUDE_CODE_SUBAGENT_MODEL")')"
  if [[ "$v" == "__ERR__" ]]; then
    warn "$f is not valid JSON — could not inspect it"
    continue
  fi
  [[ -n "$v" ]] && model_at="$f (=$v)"
  v="$(jget "$f" 'str(d.get("env", {}).get("CLAUDE_CODE_SUBAGENT_MODEL_FORCE", "")) == "1"')"
  [[ -n "$v" && "$v" != "__ERR__" ]] && force_at="$f"
done

if [[ -n "$force_at" ]]; then
  fail "CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1 is set in $force_at — every agent's model: pin is ignored and the whole tiering runs on one model"
elif [[ -n "$model_at" && -n "$CC_VERSION" ]] && version_lt "$CC_VERSION" "2.1.251"; then
  fail "CLAUDE_CODE_SUBAGENT_MODEL is set in $model_at — on Claude Code $CC_VERSION (before 2.1.251) it overrides every model pin"
elif [[ -n "$model_at" ]]; then
  warn "CLAUDE_CODE_SUBAGENT_MODEL is set in $model_at — since 2.1.251 only a default for agents with no model: pin, so the four pinned agents keep theirs; before 2.1.251 it overrode every pin"
else
  pass "no subagent model override: CLAUDE_CODE_SUBAGENT_MODEL_FORCE and CLAUDE_CODE_SUBAGENT_MODEL are unset"
fi
if [[ -f "$MANAGED" && -r "$MANAGED" ]]; then
  v="$(jget "$MANAGED" 'bool(d.get("availableModels") or d.get("modelOverrides"))')"
  if [[ -n "$v" && "$v" != "__ERR__" ]]; then
    warn "managed settings define availableModels/modelOverrides — aliases can be remapped at policy level; verify with a transcript"
  fi
fi

# ── 2. What is installed, and by which path ──────────────────────────────────
# Local files and an enabled plugin must not both be active: plugin agents are
# namespaced, so both load, and the plugin copies have lost permissionMode.

local_agents=0
for a in $ALL_AGENTS; do
  [[ -f "$TARGET/.claude/agents/$a.md" ]] && local_agents=$((local_agents + 1))
done
local_skills=0
for s in $SKILLS; do
  [[ -f "$TARGET/.claude/skills/$s/SKILL.md" ]] && local_skills=$((local_skills + 1))
done

plugin_enabled=""
for f in "$TARGET/.claude/settings.json" "$TARGET/.claude/settings.local.json" \
         "$HOME/.claude/settings.json"; do
  [[ -f "$f" && -r "$f" ]] || continue
  v="$(jget "$f" '[k for k, on in d.get("enabledPlugins", {}).items() if on and k.startswith("plan-and-execute@")]')"
  if [[ -n "$v" && "$v" != "__ERR__" && "$v" != "[]" ]]; then
    plugin_enabled="$f"
  fi
done

if [[ $local_agents -eq 4 && $local_skills -eq 2 ]]; then
  pass "local install complete: 4 agents, 2 skills under .claude/"
elif [[ $((local_agents + local_skills)) -gt 0 ]]; then
  fail "partial local install: $local_agents/4 agents, $local_skills/2 skills — re-run install.sh"
elif [[ -n "$plugin_enabled" ]]; then
  warn "no local install; running via the plugin — plugin agents drop permissionMode, so the read-only agents are only instructed not to write"
else
  fail "not installed here: no .claude/ copies and no enabled plan-and-execute plugin"
fi

if [[ $local_agents -gt 0 && -n "$plugin_enabled" ]]; then
  fail "both distribution paths active: local .claude/ copies AND plugin enabled in $plugin_enabled — the orchestrator can pick the unenforced plugin copy; disable one"
elif [[ $local_agents -gt 0 ]]; then
  pass "single distribution path: plugin not enabled alongside the local copies"
fi

# ── 3. The local agent files themselves ──────────────────────────────────────

if [[ $local_agents -gt 0 ]]; then
  for a in $READONLY_AGENTS; do
    f="$TARGET/.claude/agents/$a.md"
    [[ -f "$f" ]] || continue
    if frontmatter "$f" | grep -Eq '^permissionMode:[[:space:]]*plan[[:space:]]*$'; then
      pass "$a keeps permissionMode: plan"
    else
      fail "$a has lost permissionMode: plan — read-only is now prompt-only"
    fi
  done

  for a in $WORKER_AGENTS; do
    f="$TARGET/.claude/agents/$a.md"
    [[ -f "$f" ]] || continue
    if grep -q '<!-- PROJECT:' "$f"; then
      warn "$a still carries its PROJECT marker — the test/check wrappers and danger zones were never adapted to this project"
    else
      pass "$a is adapted (PROJECT marker replaced)"
    fi
    # An allowlist without mcp__ entries hides every MCP server (and, without
    # ToolSearch, every deferred tool). Installs from before 0.2.1 carry one,
    # and --update keeps adapted worker files, so it survives upgrades.
    tools_line="$(frontmatter "$f" | grep -E '^tools:' || true)"
    if [[ -z "$tools_line" ]]; then
      pass "$a inherits the session's tools, MCP servers included"
    elif [[ "$tools_line" == *mcp__* ]]; then
      pass "$a allowlists MCP tools explicitly"
    else
      warn "$a has a tools: allowlist with no mcp__ entries — it cannot reach any MCP server; delete the tools: line"
    fi
  done

  for a in $ALL_AGENTS; do
    f="$TARGET/.claude/agents/$a.md"
    [[ -f "$f" ]] || continue
    if ! frontmatter "$f" | grep -Eq '^model:[[:space:]]*[^[:space:]]'; then
      fail "$a has no model: pin — it will inherit the session model"
    fi
    if frontmatter "$f" | grep -Eq '^background:[[:space:]]*true'; then
      fail "$a declares background: true — it stays in the background even with background tasks disabled, so the caller reviews an empty diff and the invoking skill's pin drops"
    fi
  done
fi

# Foreground delegation. Since 2.1.232 an interactive session backgrounds every
# subagent and nothing in an agent file can ask for the foreground; the
# documented switch is CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1, in settings env
# or the shell. A backgrounded completion starts a new turn at the session
# model/effort, which is where the skill's pin is lost.
bg_off=""
for f in "$TARGET/.claude/settings.json" "$TARGET/.claude/settings.local.json" \
         "$HOME/.claude/settings.json"; do
  [[ -f "$f" && -r "$f" ]] || continue
  v="$(jget "$f" 'd.get("env", {}).get("CLAUDE_CODE_DISABLE_BACKGROUND_TASKS")')"
  [[ "$v" == "1" ]] && bg_off="$f"
done
if [[ "${CLAUDE_CODE_DISABLE_BACKGROUND_TASKS:-}" == "1" ]]; then
  pass "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 is set in this shell — delegations return in the foreground (shell-only; put it in settings env to make it standing)"
elif [[ -n "$bg_off" ]]; then
  pass "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 in $bg_off — delegations return in the foreground and the skill's model/effort pin holds"
elif [[ "${CLAUDE_CODE_FORK_SUBAGENT:-}" == "0" ]]; then
  warn "CLAUDE_CODE_FORK_SUBAGENT=0 — fork mode off, so Claude may foreground a delegation it needs; not a guarantee — set CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 instead (templates/settings.snippet.json)"
else
  fail "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS is not set — every delegation is backgrounded, the skill's model/effort pin drops at the first completion notification (templates/settings.snippet.json)"
fi
if [[ -n "${CLAUDE_CODE_EFFORT_LEVEL:-}" ]]; then
  warn "CLAUDE_CODE_EFFORT_LEVEL=$CLAUDE_CODE_EFFORT_LEVEL is set — it overrides /effort, settings and skill/agent frontmatter effort alike"
fi

if [[ $local_skills -gt 0 ]]; then
  skills_ok=1
  for s in $SKILLS; do
    f="$TARGET/.claude/skills/$s/SKILL.md"
    [[ -f "$f" ]] || continue
    if ! frontmatter "$f" | grep -Eq '^model:[[:space:]]*[^[:space:]]'; then
      fail "skill $s has no model: pin"
      skills_ok=0
    fi
    if ! frontmatter "$f" | grep -Eq '^disable-model-invocation:[[:space:]]*true'; then
      warn "skill $s lacks disable-model-invocation: true — its body loads even when not invoked"
      skills_ok=0
    fi
  done
  if [[ $skills_ok -eq 1 ]]; then
    pass "both skills carry their model pin and stay unloaded until invoked"
  fi
fi

# ── 4. Settings this workflow recommends ─────────────────────────────────────

psettings="$TARGET/.claude/settings.json"
if [[ -f "$psettings" ]]; then
  v="$(jget "$psettings" 'd.get("plansDirectory")')"
  if [[ "$v" == "__ERR__" ]]; then
    warn "$psettings is not valid JSON"
  elif [[ -z "$v" ]]; then
    warn "plansDirectory not set — built-in plan mode writes to ~/.claude/plans/, outside version control (templates/settings.snippet.json)"
  elif [[ "$v" == /* || "$v" == *..* ]]; then
    fail "plansDirectory is '$v' — must be relative and inside the project root, or it is rejected"
  else
    pass "plansDirectory: $v"
  fi
else
  warn "no $psettings — plansDirectory not set (templates/settings.snippet.json)"
fi

if [[ -f "$TARGET/CLAUDE.md" ]] && grep -q '/execute-plan' "$TARGET/CLAUDE.md"; then
  pass "CLAUDE.md carries the routing line for saved plans"
else
  warn "CLAUDE.md does not mention /execute-plan — add the two-line snippet (templates/CLAUDE.md.snippet.md)"
fi

# Optional: the worker rows under the prompt. Without it a running worker shows
# its name and a token count and nothing of what it is doing.
ssl_at=""
for f in "$TARGET/.claude/settings.json" "$TARGET/.claude/settings.local.json" \
         "$HOME/.claude/settings.json"; do
  [[ -f "$f" && -r "$f" ]] || continue
  v="$(jget "$f" '(d.get("subagentStatusLine") or {}).get("command")')"
  [[ -n "$v" && "$v" != "__ERR__" && "$v" == *subagent-statusline.py* ]] && ssl_at="$f"
done
ssl_script="$TARGET/.claude/plan-and-execute/subagent-statusline.py"
if [[ -n "$ssl_at" && -f "$ssl_script" ]]; then
  pass "subagentStatusLine in $ssl_at — each worker's row shows what it is doing"
elif [[ -n "$ssl_at" ]]; then
  warn "subagentStatusLine in $ssl_at points at subagent-statusline.py, but .claude/plan-and-execute/subagent-statusline.py is missing — re-run install.sh"
else
  info "subagentStatusLine not set — optional; with it each worker's row shows its current action, files changed and last check (templates/settings.snippet.json)"
fi

# ── 5. Test/check wrappers ────────────────────────────────────────────────────
# The worker agents are written against bin/test-<lang> and bin/check-<lang>.

shopt -s nullglob
wrappers=("$TARGET"/bin/test-* "$TARGET"/bin/check-*)
shopt -u nullglob

run_probe() { if command -v timeout >/dev/null; then timeout 10 "$@"; else "$@"; fi; }

if [[ ${#wrappers[@]} -eq 0 ]]; then
  warn "no bin/test-* or bin/check-* wrappers — the worker agents reference them; add wrappers or adapt the agent files (templates/bin/test-example.sh)"
else
  for w in "${wrappers[@]}"; do
    name="${w#"$TARGET"/}"
    if [[ ! -x "$w" ]]; then
      warn "$name is not executable"
      continue
    fi
    if [[ $PROBE -eq 1 ]]; then
      if run_probe "$w" </dev/null >/dev/null 2>&1; then
        fail "$name ran with NO target and exited 0 — nothing stops an agent from launching the full suite"
      elif run_probe "$w" "" </dev/null >/dev/null 2>&1; then
        fail "$name accepted an EMPTY-STRING target — an unset shell variable slips through the argument-count check"
      else
        pass "$name refuses a missing and an empty target"
      fi
    else
      pass "$name present and executable (static check only — --probe to verify it refuses an empty target)"
    fi
  done
fi

# ── 6. Plugin snapshot staleness ─────────────────────────────────────────────
# A directory-source plugin is copied into ~/.claude/plugins/cache/ at install
# time; editing the repo afterwards changes nothing that Claude Code loads.

INSTALLED="$HOME/.claude/plugins/installed_plugins.json"
if [[ -n "$plugin_enabled" && -f "$INSTALLED" ]]; then
  cache="$(jget "$INSTALLED" 'next((e[0].get("installPath") for k, e in d.get("plugins", {}).items() if k.startswith("plan-and-execute@") and e), None)')"
  if [[ -n "$cache" && "$cache" != "__ERR__" && -d "$cache" ]]; then
    stale=0
    for rel in skills/make-plan/SKILL.md skills/execute-plan/SKILL.md \
               agents/planning-researcher.md agents/plan-reviewer.md; do
      if [[ -f "$cache/$rel" ]] && ! diff -q "$SRC/$rel" "$cache/$rel" >/dev/null 2>&1; then
        stale=1
      fi
    done
    if [[ $stale -eq 1 ]]; then
      warn "plugin cache at $cache differs from this repo — the installed plugin is a stale snapshot; reinstall it"
    else
      pass "plugin cache matches this repo"
    fi
  fi
fi

# ── 7. Version, informational ────────────────────────────────────────────────
# The newest version this repo records a measurement on: the highest version
# number its README sets in bold.

if [[ -n "$CC_VERSION" ]]; then
  tested="$(grep -oE '\*\*[0-9]+\.[0-9]+\.[0-9]+\*\*' "$SRC/README.md" 2>/dev/null \
            | tr -d '*' | sort -t. -k1,1n -k2,2n -k3,3n | tail -1)"
  if [[ -n "$tested" ]] && version_lt "$tested" "$CC_VERSION"; then
    info "Claude Code $CC_VERSION installed; this repo's newest measurements are on $tested — behaviour can drift between versions"
  else
    info "Claude Code $CC_VERSION"
  fi
fi

echo
echo "$npass pass, $nwarn warn, $nfail fail"
[[ $nfail -eq 0 ]]
