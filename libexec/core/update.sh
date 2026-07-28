#!/usr/bin/env bash
# tess self-update. Runs in the background on any tess command (throttled to ~6h),
# and foreground with output via `tess update`.
set -uo pipefail

# resolve the repo (this script lives in <repo>/libexec/core, possibly via symlink)
src="${BASH_SOURCE[0]}"; while [ -L "$src" ]; do src="$(readlink "$src")"; done
REPO="$(cd "$(dirname "$src")/../.." 2>/dev/null && pwd)"
[ -d "$REPO/.git" ] || exit 0

force="${1:-}"
stamp="$HOME/.config/tess/.last-update"

# Opt out of the background self-update: TESS_NO_AUTOUPDATE=1 in ~/.config/tess/config (or the
# environment). `tess update` still works — this only disables the unattended pull, for people
# who'd rather decide when their tooling changes under them.
if [ "$force" != "--now" ] && [ "${TESS_NO_AUTOUPDATE:-}" = "1" ]; then exit 0; fi

if [ "$force" != "--now" ]; then
  now=$(date +%s)
  last=$(stat -f %m "$stamp" 2>/dev/null || stat -c %Y "$stamp" 2>/dev/null || echo 0)
  [ $((now - last)) -lt 21600 ] && exit 0            # throttle: at most once / 6h
fi
mkdir -p "$(dirname "$stamp")"; touch "$stamp"

before=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo "")
# --ff-only + never touch a dirty tree: safe, won't clobber local edits/commits
git -C "$REPO" pull --quiet --ff-only 2>/dev/null || { [ "$force" = "--now" ] && echo "tess: up to date or local changes present (skipped)"; exit 0; }
after=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo "")

if [ "$force" = "--now" ]; then
  if [ "$before" != "$after" ]; then echo "tess updated: $before → $after"; else echo "tess already up to date ($after)"; fi
fi
