#!/usr/bin/env bash
# tess wire — teach every AI coding agent on this machine about tess.
#
# Three layers, strongest first:
#   1. SKILLS   portable SKILL.md, loaded on demand (Claude Code · Cursor · Codex · Gemini ·
#               opencode). This is the main payload — it costs zero tokens until it's relevant.
#   2. HOOKS    a shell guard that blocks raw `git worktree` and redirects to `tess new`
#               (Claude Code + Cursor — the only two with a pre-shell hook today).
#   3. PRIMER   agent-primer.md injected into the instruction file for agents with neither
#               (Kimi, Codex AGENTS.md, plain AGENTS.md consumers).
#
# Idempotent — safe to re-run. `--dry-run` shows the plan and changes nothing.
# Symlinks, not copies: `tess update` refreshes every wired agent for free.
set -uo pipefail

HERE="${TESS_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
DRY=0; UNDO=0
for a in "$@"; do case "$a" in
  --dry-run|-n) DRY=1 ;;
  --undo)       UNDO=1 ;;
  -h|--help) echo "usage: tess wire [--dry-run] [--undo]"; exit 0 ;;
esac; done

if [ -t 1 ]; then B=$'\033[1m'; D=$'\033[2m'; R=$'\033[0m'; G=$'\033[32m'; Y=$'\033[33m'
else B=; D=; R=; G=; Y=; fi

say()  { printf '  %s\n' "$*"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$R" "$*"; }
skip() { printf '  %s·%s %s %s(%s)%s\n' "$D" "$R" "$1" "$D" "$2" "$R"; }
run()  { [ "$DRY" = 1 ] && { printf '  %s→ would: %s%s\n' "$D" "$*" "$R"; return 0; }; "$@"; }

[ "$DRY" = 1 ] && echo "${Y}dry run — nothing will be changed${R}"

# ---------------------------------------------------------------- 1. skills --
# ~/.agents/skills is the portable location (Cursor and Codex both read it). The
# per-tool dirs are linked too, for hosts that only scan their own.
SKILL_ROOTS=(
  "$HOME/.agents/skills"              # portable standard — always
  "$HOME/.claude/skills"              # Claude Code
  "$HOME/.cursor/skills"              # Cursor
  "$HOME/.codex/skills"               # Codex
  "$HOME/.gemini/skills"              # Gemini CLI
  "$HOME/.config/opencode/skills"     # opencode
)

echo "${B}skills${R} ${D}— the main payload; loads only when the task calls for it${R}"
for root in "${SKILL_ROOTS[@]}"; do
  parent="$(dirname "$root")"
  # always set up the portable root; per-tool roots only if that tool exists
  if [ "$root" != "$HOME/.agents/skills" ] && [ ! -d "$parent" ]; then
    skip "${parent/#$HOME/~}" "not installed"; continue
  fi
  run mkdir -p "$root" 2>/dev/null
  for s in "$HERE"/skills/*/; do
    name="$(basename "$s")"; link="$root/$name"
    if [ "$UNDO" = 1 ]; then
      [ -L "$link" ] && run rm -f "$link"
      continue
    fi
    # only ever touch our own symlinks — never clobber a real directory
    if [ -e "$link" ] && [ ! -L "$link" ]; then
      skip "$name → ${root/#$HOME/~}" "a real dir is already there"; continue
    fi
    run ln -sfn "${s%/}" "$link"
  done
  [ "$UNDO" = 1 ] && ok "unlinked from ${root/#$HOME/~}" || ok "${root/#$HOME/~}"
done

# ----------------------------------------------------------------- 2. hooks --
echo
echo "${B}guardrail${R} ${D}— blocks raw \`git worktree\`, redirects to \`tess new\`${R}"

# Claude Code: skip entirely when the tess PLUGIN is installed — it ships the same
# hook, and wiring both would double-fire.
_plugin_installed() {
  grep -lq '"tess"' "$HOME/.claude/plugins/config.json" \
    "$HOME/.claude/plugins/installed_plugins.json" 2>/dev/null
}
if [ ! -d "$HOME/.claude" ]; then
  skip "Claude Code" "not installed"
elif _plugin_installed; then
  skip "Claude Code" "the tess plugin already provides it"
else
  run python3 "$HERE/libexec/core/wire_claude.py" "$HERE" "$([ "$UNDO" = 1 ] && echo --undo)"
fi

# Cursor: merge into ~/.cursor/hooks.json (never overwrite — users have their own)
if [ ! -d "$HOME/.cursor" ]; then
  skip "Cursor" "not installed"
else
  run python3 "$HERE/libexec/core/wire_cursor.py" "$HERE" "$([ "$UNDO" = 1 ] && echo --undo)"
fi

skip "Codex · Kimi · Gemini" "no pre-shell hook API — covered by skills + primer"

# ---------------------------------------------------------------- 3. primer --
echo
echo "${B}primer${R} ${D}— for agents without skill support${R}"
_primer() {
  [ -d "$(dirname "$1")" ] || { skip "$2" "not installed"; return; }
  if [ "$DRY" = 1 ]; then printf '  %s→ would inject primer into %s%s\n' "$D" "${1/#$HOME/~}" "$R"; return; fi
  python3 "$HERE/libexec/core/wire_primer.py" "$1" "$HERE/agent-primer.md" "$([ "$UNDO" = 1 ] && echo --undo)"
}
_primer "$HOME/.claude/CLAUDE.md"      "Claude Code"
_primer "$HOME/.kimi-code/AGENTS.md"   "Kimi"
_primer "$HOME/.codex/AGENTS.md"       "Codex"
_primer "$HOME/.gemini/GEMINI.md"      "Gemini"

echo
if [ "$UNDO" = 1 ]; then echo "${B}unwired.${R} Skills unlinked, hooks and primers removed."
elif [ "$DRY" = 1 ]; then echo "run without ${B}--dry-run${R} to apply."
else
  echo "${B}done.${R} Restart any running agent session to pick it up."
  echo "${D}re-run anytime (it's idempotent) · undo with: tess wire --undo${R}"
fi
