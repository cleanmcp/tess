#!/usr/bin/env bash
# tess uninstaller — removes everything install.sh added, and nothing else.
#
#   ./uninstall.sh              interactive: asks before each destructive step
#   ./uninstall.sh --yes        no prompts (still never touches your worktrees or repos)
#
# What it will NOT touch, ever:
#   • your source repos
#   • your feature worktrees (they're real git worktrees with real work in them)
#   • your notes vault
# Those are yours. It prints where they are and leaves them alone.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
YES="${1:-}"

if [ -t 1 ]; then B=$'\033[1m'; D=$'\033[2m'; R=$'\033[0m'; G=$'\033[32m'; Y=$'\033[33m'
else B=; D=; R=; G=; Y=; fi
# Read the config BEFORE anything deletes it — it's the only record of where the user's
# worktrees and vault live, and we need that to tell them what we're leaving behind.
# shellcheck disable=SC1091
[ -f "$HOME/.config/tess/config" ] && . "$HOME/.config/tess/config" 2>/dev/null

say()  { printf "\033[36m%s\033[0m\n" "$*"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$R" "$*"; }
skip() { printf '  %s·%s %s\n' "$D" "$R" "$*"; }
ask()  { [ "$YES" = "--yes" ] && return 0; printf "%s%s%s [y/N] " "$B" "$*" "$R"; read -r a; [[ "$a" =~ ^[Yy]$ ]]; }

echo
say "› unwiring tess from your AI agents"
# removes the skills symlinks, the guardrail hooks, and the primer blocks
if [ -x "$HERE/libexec/core/wire.sh" ]; then
  bash "$HERE/libexec/core/wire.sh" --undo 2>&1 | sed 's/^/  /'
else
  skip "wire.sh not found — remove skills/hooks by hand if you wired them"
fi

say "› removing the tess command"
if [ -L "$BIN/tess" ]; then
  rm -f "$BIN/tess"; ok "removed $BIN/tess"
else
  skip "no $BIN/tess symlink"
fi

say "› config and state (~/.config/tess)"
CFG="$HOME/.config/tess"
if [ -d "$CFG" ]; then
  echo "  this holds your config, your custom commands, your todos and the budget ledger:"
  du -sh "$CFG" 2>/dev/null | sed 's/^/    /'
  if ask "  delete ~/.config/tess?"; then
    rm -rf "$CFG"; ok "removed ~/.config/tess"
  else
    skip "kept ~/.config/tess — a re-install picks up right where you left off"
  fi
else
  skip "no ~/.config/tess"
fi

# --- what we deliberately leave behind ---------------------------------------
echo
echo "${B}left alone (yours, not tess's):${R}"
WT="${TESS_WORKTREE_ROOT:-$HOME/worktrees}"
if [ -d "$WT" ] && [ -n "$(ls -A "$WT" 2>/dev/null)" ]; then
  echo "  ${Y}worktrees${R}  ${WT/#$HOME/~}"
  echo "  ${D}  these are real git worktrees with real branches. Remove them deliberately:${R}"
  echo "  ${D}  tess rm <feature>   (before uninstalling), or  git worktree remove <path>${R}"
fi
echo "  ${Y}this checkout${R}  ${HERE/#$HOME/~}   ${D}(delete it yourself: rm -rf ${HERE/#$HOME/~})${R}"
[ -n "${TESS_VAULT:-}" ] && echo "  ${Y}notes vault${R}  ${TESS_VAULT/#$HOME/~}   ${D}(untouched)${R}"

echo
echo "${B}done.${R} ${D}Reinstall any time: ./install.sh${R}"
echo "${D}If you added ~/.local/bin to your PATH just for tess, you can drop that line from your shell rc.${R}"
