#!/usr/bin/env bash
#
# Install the plan-and-execute agents and skills into a project.
#
#   ./install.sh /path/to/project           install, refuse to overwrite
#   ./install.sh /path/to/project --update  take upstream changes, keep local edits
#   ./install.sh /path/to/project --force   overwrite existing files
#   ./install.sh /path/to/project --templates    also copy templates/
#   ./install.sh /path/to/project --skills-only  skills only, leave agents alone
#   ./install.sh /path/to/project --uninstall    remove what install placed
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
# --update does make one edit to those two files: if an adapted worker agent's
# frontmatter has no `background:` key it inserts `background: false` after the
# `model:` line and says so. Without it the delegation is backgrounded, the
# orchestrator reviews an empty diff, and the invoking skill's model/effort pin
# drops at the completion notification. An existing `background:` value of any
# kind is left alone.
#
# --uninstall removes exactly the files install places. Worker agents that were
# adapted to the project survive unless --force is added; plans/, the CLAUDE.md
# snippet, and .claude/settings.json are never touched.
#
# Idempotent: a second run without --force changes nothing and says so.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TARGET=""
FORCE=0
TEMPLATES=0
SKILLS_ONLY=0
UPDATE=0
UNINSTALL=0

# Agents that name project-specific commands and danger zones. --update leaves
# these alone; they are supposed to differ per project.
PROJECT_LOCAL_AGENTS="implementer quick-implementer"

for arg in "$@"; do
  case "$arg" in
    --force)       FORCE=1 ;;
    --update)      UPDATE=1; FORCE=1 ;;
    --templates)   TEMPLATES=1 ;;
    --skills-only) SKILLS_ONLY=1 ;;
    --uninstall)   UNINSTALL=1 ;;
    -h|--help)
      sed -n '2,33p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    -*)
      echo "unknown option: $arg" >&2; exit 2 ;;
    *)
      if [[ -n "$TARGET" ]]; then echo "more than one target given" >&2; exit 2; fi
      TARGET="$arg" ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "usage: $(basename "$0") <project-dir> [--force] [--templates] [--update] [--uninstall]" >&2
  exit 2
fi

if [[ $UNINSTALL -eq 1 && $UPDATE -eq 1 ]]; then
  echo "--uninstall and --update do not combine" >&2
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
patched=0

is_project_local() {         # is_project_local <agent-name>
  local name="$1" a
  for a in $PROJECT_LOCAL_AGENTS; do
    [[ "$name" == "$a" ]] && return 0
  done
  return 1
}

# --update never overwrites an adapted worker agent, so an upstream frontmatter
# line never reaches one. This is the line that has to be there.
ensure_background() {        # ensure_background <agent-file>
  local dest="$1" fm tmp
  fm="$(awk '/^---[[:space:]]*$/ { n++; next } n == 1 { print } n >= 2 { exit }' "$dest")"
  if grep -Eq '^background:' <<<"$fm"; then
    return 0
  fi
  if ! grep -Eq '^model:' <<<"$fm"; then
    echo "  note     ${dest#"$TARGET"/}  (no model: line in frontmatter — add 'background: false' by hand)"
    return 0
  fi
  tmp="$dest.plan-and-execute.tmp"
  awk '
    /^---[[:space:]]*$/ { n++ }
    { print }
    n == 1 && !done && /^model:/ { print "background: false"; done = 1 }
  ' "$dest" > "$tmp" && mv "$tmp" "$dest"
  echo "  patch    ${dest#"$TARGET"/}  (inserted background: false — delegations must return in the foreground)"
  patched=$((patched + 1))
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

if [[ $UNINSTALL -eq 1 ]]; then
  removed=0
  kept=0

  echo "Uninstalling from $TARGET"

  if [[ $SKILLS_ONLY -eq 0 ]]; then
    for f in "$SRC"/agents/*.md; do
      name="$(basename "$f" .md)"
      dest="$TARGET/.claude/agents/$name.md"
      [[ -e "$dest" ]] || continue
      # Same test as --update: the PROJECT marker's absence is the evidence of
      # adaptation, not a diff against upstream.
      if is_project_local "$name" && [[ $FORCE -eq 0 ]] \
         && ! grep -q '<!-- PROJECT:' "$dest" 2>/dev/null; then
        echo "  keep     .claude/agents/$name.md  (adapted to this project — add --force to remove)"
        kept=$((kept + 1))
        continue
      fi
      rm "$dest"
      echo "  remove   .claude/agents/$name.md"
      removed=$((removed + 1))
    done
  fi

  for d in "$SRC"/skills/*/; do
    name="$(basename "$d")"
    dest="$TARGET/.claude/skills/$name/SKILL.md"
    if [[ -e "$dest" ]]; then
      rm "$dest"
      echo "  remove   .claude/skills/$name/SKILL.md"
      removed=$((removed + 1))
    fi
    rmdir "$TARGET/.claude/skills/$name" 2>/dev/null || true
  done

  tpl_dir="$TARGET/.claude/plan-and-execute-templates"
  if [[ -d "$tpl_dir" ]]; then
    # Remove only the paths install places; a file the user dropped or created
    # in here is not ours to delete, --force or not.
    tpl_removed=0
    while IFS= read -r f; do
      rel="${f#"$SRC"/templates/}"
      if [[ -e "$tpl_dir/$rel" ]]; then
        rm "$tpl_dir/$rel"
        tpl_removed=$((tpl_removed + 1))
      fi
    done < <(find "$SRC/templates" -type f | sort)
    find "$tpl_dir" -depth -type d -empty -delete 2>/dev/null || true
    if [[ $tpl_removed -gt 0 ]]; then
      echo "  remove   .claude/plan-and-execute-templates/  ($tpl_removed files)"
      removed=$((removed + tpl_removed))
    fi
    if [[ -d "$tpl_dir" ]]; then
      echo "  keep     .claude/plan-and-execute-templates/  (contains files install.sh did not place)"
      kept=$((kept + 1))
    fi
  fi

  # Only ever removes empty directories; anything else in them survives.
  rmdir "$TARGET/.claude/agents" "$TARGET/.claude/skills" 2>/dev/null || true

  echo
  if [[ $removed -eq 0 && $kept -eq 0 ]]; then
    echo "Nothing to remove."
  else
    summary="$removed removed"
    [[ $kept -gt 0 ]] && summary="$summary, $kept kept"
    echo "$summary."
    echo
    echo "Left in place, on purpose: plans/, the CLAUDE.md routing snippet, and"
    echo "any plansDirectory or permissions entries in .claude/settings.json."
  fi
  exit 0
fi

echo "Installing into $TARGET"

if [[ $SKILLS_ONLY -eq 0 ]]; then
  for f in "$SRC"/agents/*.md; do
    name="$(basename "$f" .md)"
    dest="$TARGET/.claude/agents/$name.md"

    if [[ $UPDATE -eq 1 && -e "$dest" ]] && is_project_local "$name"; then
      # Test the PROJECT marker, not a diff against upstream. A file can differ
      # from this repo's copy merely by being an older install, so a difference
      # is not evidence of adaptation — the marker's absence is.
      if grep -q '<!-- PROJECT:' "$dest" 2>/dev/null; then
        echo "  keep     .claude/agents/$name.md  (NOT adapted — still has its PROJECT marker)"
      else
        echo "  keep     .claude/agents/$name.md  (project-specific; left alone)"
      fi
      kept=$((kept + 1))
      ensure_background "$dest"
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
[[ $patched -gt 0 ]] && summary="$summary, $patched patched"
echo "$summary."

if [[ $written -eq 0 && $patched -eq 0 ]]; then
  echo "Nothing changed."
  exit 0
fi

if [[ $UPDATE -eq 1 ]]; then
  cat <<EOF

Skills and agents are read when a session starts, so restart Claude Code in
$TARGET before the change takes effect.

The kept agents do not pick up upstream edits. If this repo changed something
in them that matters — a report format, a stopping rule — merge it by hand:
EOF
  for name in $PROJECT_LOCAL_AGENTS; do
    dest="$TARGET/.claude/agents/$name.md"
    [[ -e "$dest" ]] || continue
    printf '  diff %q %q\n' "$SRC/agents/$name.md" "$dest"
  done
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
