#!/usr/bin/env bash
#
# Install the plan-and-execute agents and skills into a project.
#
#   ./install.sh /path/to/project           install, refuse to overwrite
#   ./install.sh /path/to/project --update  take upstream changes, keep local edits
#   ./install.sh /path/to/project --force   overwrite existing files
#   ./install.sh /path/to/project --templates    also copy templates/
#   ./install.sh /path/to/project --skills-only  skills only, leave agents alone
#
# Copies:
#   agents/*.md          -> <project>/.claude/agents/
#   skills/*/SKILL.md    -> <project>/.claude/skills/<name>/SKILL.md
#
# --update is the routine "this repo changed, pull it in" path, and the one to
# reach for after a fix lands here. It overwrites the skills and the two
# read-only agents, which hold nothing project-specific, and never touches
# implementer or quick-implementer — those name the project's own test and lint
# commands and its own danger zones, so they are meant to diverge.
#
# Idempotent: a second run without --force changes nothing and says so.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TARGET=""
FORCE=0
TEMPLATES=0
SKILLS_ONLY=0
UPDATE=0

# Agents that name project-specific commands and danger zones. --update leaves
# these alone; they are supposed to differ per project.
PROJECT_LOCAL_AGENTS="implementer quick-implementer"

for arg in "$@"; do
  case "$arg" in
    --force)       FORCE=1 ;;
    --update)      UPDATE=1; FORCE=1 ;;
    --templates)   TEMPLATES=1 ;;
    --skills-only) SKILLS_ONLY=1 ;;
    -h|--help)
      sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    -*)
      echo "unknown option: $arg" >&2; exit 2 ;;
    *)
      if [[ -n "$TARGET" ]]; then echo "more than one target given" >&2; exit 2; fi
      TARGET="$arg" ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "usage: $(basename "$0") <project-dir> [--force] [--templates]" >&2
  exit 2
fi

if [[ ! -d "$TARGET" ]]; then
  echo "not a directory: $TARGET" >&2
  exit 1
fi

TARGET="$(cd "$TARGET" && pwd)"

if [[ "$TARGET" == "$SRC" ]]; then
  echo "target is this repository; nothing to do" >&2
  exit 1
fi

if [[ ! -d "$TARGET/.git" ]]; then
  echo "warning: $TARGET is not a git repository."
  echo "         The workflow depends on git status and diffs to review each phase."
fi

written=0
skipped=0
kept=0

is_project_local() {         # is_project_local <agent-name>
  local name="$1" a
  for a in $PROJECT_LOCAL_AGENTS; do
    [[ "$name" == "$a" ]] && return 0
  done
  return 1
}

place() {                     # place <source-file> <dest-file>
  local src="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$dest" && $FORCE -eq 0 ]]; then
    echo "  skip     ${dest#"$TARGET"/}  (exists — use --force to overwrite)"
    skipped=$((skipped + 1))
    return
  fi
  cp "$src" "$dest"
  echo "  write    ${dest#"$TARGET"/}"
  written=$((written + 1))
}

echo "Installing into $TARGET"

if [[ $SKILLS_ONLY -eq 0 ]]; then
  for f in "$SRC"/agents/*.md; do
    name="$(basename "$f" .md)"
    dest="$TARGET/.claude/agents/$name.md"

    if [[ $UPDATE -eq 1 && -e "$dest" ]] && is_project_local "$name"; then
      if diff -q "$f" "$dest" >/dev/null 2>&1; then
        echo "  keep     .claude/agents/$name.md  (project-specific; not adapted yet)"
      else
        echo "  keep     .claude/agents/$name.md  (project-specific; adapted locally)"
      fi
      kept=$((kept + 1))
      continue
    fi

    place "$f" "$dest"
  done
else
  echo "  (--skills-only: agents left untouched)"
fi

for d in "$SRC"/skills/*/; do
  name="$(basename "$d")"
  place "$d/SKILL.md" "$TARGET/.claude/skills/$name/SKILL.md"
done

if [[ $TEMPLATES -eq 1 ]]; then
  while IFS= read -r f; do
    rel="${f#"$SRC"/templates/}"
    place "$f" "$TARGET/.claude/plan-and-execute-templates/$rel"
  done < <(find "$SRC/templates" -type f | sort)
fi

echo
summary="$written written, $skipped skipped"
[[ $kept -gt 0 ]] && summary="$summary, $kept kept (project-specific)"
echo "$summary."

if [[ $written -eq 0 ]]; then
  echo "Nothing changed."
  exit 0
fi

if [[ $UPDATE -eq 1 ]]; then
  cat <<EOF

Skills and agents are read when a session starts, so restart Claude Code in
$TARGET before the change takes effect.

The kept agents do not pick up upstream edits. If this repo changed something
in them that matters — a report format, a stopping rule — merge it by hand:

  diff $SRC/agents/implementer.md $TARGET/.claude/agents/implementer.md
EOF
  exit 0
fi

cat <<EOF

Next:

  1. Adapt the two worker agents to this project. Both contain a
     "<!-- PROJECT: ... -->" marker naming what to replace — the test and check
     wrapper commands, and the danger zones quick-implementer must refuse.

  2. Add the routing line to $TARGET/CLAUDE.md:

       ## Saved plans

       Saved implementation plans are executed only through the explicitly
       invoked \`/execute-plan <plan-file>\` skill. The orchestration procedure
       lives in that skill, not here.

  3. Do not set CLAUDE_CODE_SUBAGENT_MODEL. It overrides every agent's model
     pin and collapses the tiering onto a single model.

  4. Run it:

       /make-plan MyPlan <the problem>
       # then, in a fresh session:
       /execute-plan plans/MyPlan.md
EOF
