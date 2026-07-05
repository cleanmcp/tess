#!/usr/bin/env bash
#
# worktree.sh — spin up a matching git worktree for every configured repo
# so you can work on the same feature across all of them at once. Untracked
# env files (.env, .env.local, ...) are copied from each source repo into its
# new worktree, since `git worktree` never carries untracked files along.
#
# Usage:
#   ./worktree.sh <feature-name> [base-branch]
#   ./worktree.sh rm <feature-name>        # remove the worktrees again
#
# Examples:
#   ./worktree.sh linkedin-export          # branch off "main" in each repo
#   ./worktree.sh hotfix-login develop     # branch off "develop" instead
#   ./worktree.sh rm linkedin-export       # tear it all back down
#
# Worktrees land at:  <worktree-root>/<feature-name>/<repo>
#
set -euo pipefail
[ -f "$HOME/.config/tess/config" ] && . "$HOME/.config/tess/config"

# --- config ------------------------------------------------------------------
WORKTREE_PARENT="${TESS_WORKTREE_ROOT:-$HOME/worktrees}"
CORE_DIR="${TESS_CORE:-$WORKTREE_PARENT/repos}"

# the repos to fan out across (folders directly under your repos dir).
# default = the two you actually work on; pass --all (or --web) to add the website.
read -r -a REPOS <<< "${TESS_REPOS:-}"

# env files are discovered recursively at copy time (see copy_env_files),
# so nested ones (e.g. a sub-app's .env.local) are carried over too.

# branch every worktree off this by default (override with the 2nd arg)
DEFAULT_BASE="main"

# include the website repo only when explicitly asked: `worktree.sh --all <feature>`
if [ "${1:-}" = "--all" ] || [ "${1:-}" = "--web" ]; then
  read -r -a _opt <<< "${TESS_REPOS_ALL:-${TESS_REPOS:-}}"; REPOS=("${_opt[@]}"); shift
fi

usage() { sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'; }
case "${1:-}" in -h|--help) usage; exit 0 ;; esac

# a feature name must never be a flag (--help once created a junk worktree) or
# anything path-unsafe — this script is also called directly, so guard here too.
check_name() {
  case "${1:-}" in
    ""  ) return 0 ;;  # caller handles its own "missing name" usage error
    -*  ) c_red "refusing feature name '$1' — looks like a flag. (help: $0 --help)"; exit 2 ;;
    .*|*/*|*[!A-Za-z0-9._-]*) c_red "refusing feature name '$1' — letters, digits, . _ - only"; exit 2 ;;
  esac
}

# --- helpers -----------------------------------------------------------------
c_blue()  { printf "\033[34m%s\033[0m\n" "$*"; }
c_green() { printf "\033[32m%s\033[0m\n" "$*"; }
c_yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
c_red()   { printf "\033[31m%s\033[0m\n" "$*" >&2; }

copy_env_files() {
  local src="$1" dst="$2" copied=0 f rel
  # Find every REAL env file (.env, .env.local, .env.production, nested ones, ...)
  # but skip committed templates (*.example / *.sample) and dependency/build dirs.
  while IFS= read -r -d '' f; do
    rel="${f#"$src"/}"
    mkdir -p "$dst/$(dirname "$rel")"
    cp -p "$f" "$dst/$rel"
    echo "      copied $rel"
    copied=1
  done < <(
    find "$src" \
      \( -name node_modules -o -name .git -o -name .next -o -name dist -o -name build \) -prune -o \
      -type f \( -name '.env' -o -name '.env.*' \) \
      ! -name '*.example' ! -name '*.sample' -print0
  )
  [ "$copied" -eq 0 ] && echo "      (no env files to copy)"
  return 0
}

# --- remove mode -------------------------------------------------------------
if [ "${1:-}" = "rm" ]; then
  FEATURE="${2:-}"
  [ -z "$FEATURE" ] && { c_red "usage: $0 rm <feature-name>"; exit 1; }
  check_name "$FEATURE"
  DEST_ROOT="$WORKTREE_PARENT/$FEATURE"
  c_blue "Removing worktrees for feature '$FEATURE'"
  for repo in "${REPOS[@]}"; do
    src="$CORE_DIR/$repo"
    dst="$DEST_ROOT/$repo"
    [ -d "$dst" ] || continue
    c_yellow "  $repo"
    git -C "$src" worktree remove --force "$dst" 2>/dev/null \
      && echo "      removed worktree" \
      || c_red "      could not remove (uncommitted changes? use git -C $src worktree remove --force)"
  done
  rmdir "$DEST_ROOT" 2>/dev/null || true
  c_green "Done."
  exit 0
fi

# --- create mode -------------------------------------------------------------
FEATURE="${1:-}"
BASE="${2:-$DEFAULT_BASE}"   # base branch to cut from (default: main)
[ -z "$FEATURE" ] && { c_red "usage: $0 <feature-name> [base-branch]"; exit 1; }
check_name "$FEATURE"

DEST_ROOT="$WORKTREE_PARENT/$FEATURE"
mkdir -p "$DEST_ROOT"

c_blue "Creating worktrees for feature '$FEATURE'  ->  $DEST_ROOT"
echo

for repo in "${REPOS[@]}"; do
  src="$CORE_DIR/$repo"
  dst="$DEST_ROOT/$repo"
  c_yellow "  $repo"

  # clone from GitHub if the source repo doesn't exist locally yet
  if [ ! -d "$src" ]; then
    c_blue "      cloning ${TESS_GIT_REMOTE:+$TESS_GIT_REMOTE/}$repo from GitHub..."
    git clone "https://github.com/${TESS_GIT_REMOTE:+$TESS_GIT_REMOTE/}$repo.git" "$src" >/dev/null
    echo "      cloned into $src"
  fi

  if [ ! -d "$src/.git" ] && ! git -C "$src" rev-parse --git-dir >/dev/null 2>&1; then
    c_red "      not a git repo, skipping"
    continue
  fi

  # clear any stale worktree registration (folder deleted manually before) so
  # re-creating the same feature doesn't hit "missing but already registered".
  git -C "$src" worktree prune 2>/dev/null || true

  if [ -e "$dst" ]; then
    c_red "      $dst already exists, skipping"
    continue
  fi

  # resolve the base branch: prefer the local branch, fall back to origin/<base>
  base_ref="$BASE"
  if ! git -C "$src" show-ref --verify --quiet "refs/heads/$BASE"; then
    if git -C "$src" show-ref --verify --quiet "refs/remotes/origin/$BASE"; then
      base_ref="origin/$BASE"
    else
      c_red "      base branch '$BASE' not found (local or origin), skipping"
      continue
    fi
  fi

  # if the feature branch already exists, attach to it; otherwise create it
  if git -C "$src" show-ref --verify --quiet "refs/heads/$FEATURE"; then
    git -C "$src" worktree add -f "$dst" "$FEATURE" >/dev/null
    echo "      worktree on existing branch '$FEATURE'"
  else
    git -C "$src" worktree add -f -b "$FEATURE" "$dst" "$base_ref" >/dev/null
    echo "      worktree on new branch '$FEATURE' (from '$base_ref')"
  fi

  copy_env_files "$src" "$dst"
  echo
done

# drop an orientation note so agents launched at the feature root understand
# the layout (the root is NOT a repo; each subfolder is a git worktree).
{
  echo "# Feature: $FEATURE"
  echo
  echo "> This folder is **not** a git repo. It holds one isolated **git worktree per repo**."
  echo "> To run git, \`cd\` into a subfolder. Each has a \`.git\` **file** (a worktree pointer) —"
  echo "> that is normal, they ARE git-tracked, on branch \`$FEATURE\`."
  echo
  echo "## Repos here"
  for repo in "${REPOS[@]}"; do
    echo "- \`$repo/\` — branch \`$FEATURE\` (source: $TESS_CORE/$repo; see its own CLAUDE.md)"
  done
  echo
  echo "Only edit inside this feature's worktrees. Source repos live in $TESS_CORE/."
} > "$DEST_ROOT/AGENTS.md"
ln -sf AGENTS.md "$DEST_ROOT/CLAUDE.md"

c_green "Done. Worktrees are in: $DEST_ROOT"
echo "Tear down later with:  $0 rm $FEATURE"
