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
# config fills in what the environment didn't set — env always wins
if [ -f "$HOME/.config/tess/config" ]; then
  _pre="$(env | grep '^TESS_' || true)"
  . "$HOME/.config/tess/config"
  while IFS='=' read -r _k _v; do [ -n "$_k" ] && eval "$_k=\$_v"; done <<< "$_pre"
fi

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
  [ -d "$DEST_ROOT" ] || { c_red "no feature '$FEATURE' at $DEST_ROOT"; exit 1; }
  c_blue "Removing worktrees for feature '$FEATURE'"
  # remove what's actually THERE (not just the configured repo list, so
  # features created with --all or an older config tear down fully too)
  for dst in "$DEST_ROOT"/*/; do
    [ -d "$dst" ] || continue
    repo="$(basename "$dst")"; src="$CORE_DIR/$repo"
    # single-repo features live outside the fleet dir — follow the worktree's own pointer
    if [ ! -d "$src" ] && [ -f "${dst%/}/.git" ]; then
      gd="$(sed -n 's/^gitdir: //p' "${dst%/}/.git" 2>/dev/null)"
      case "$gd" in */.git/worktrees/*) src="${gd%/.git/worktrees/*}" ;; esac
    fi
    c_yellow "  $repo"
    if [ -d "$src" ] && git -C "$src" worktree remove --force "${dst%/}" 2>/dev/null; then
      echo "      removed worktree"
      git -C "$src" worktree prune 2>/dev/null || true
    elif [ ! -e "$dst/.git" ] && rmdir "${dst%/}" 2>/dev/null; then
      echo "      removed empty folder (was not a worktree)"
    else
      c_red "      could not remove — try: git -C $src worktree remove --force ${dst%/}"
    fi
  done
  # the folder shell: orientation files tess wrote, then the dir itself
  rm -f "$DEST_ROOT/AGENTS.md" "$DEST_ROOT/CLAUDE.md"
  if rmdir "$DEST_ROOT" 2>/dev/null; then
    c_green "Done — '$FEATURE' fully removed."
  else
    c_yellow "  folder kept, it still contains:"
    ls -A "$DEST_ROOT" | sed 's/^/      /'
    echo "      (review, then: rm -rf $DEST_ROOT)"
  fi
  exit 0
fi

# --- create mode -------------------------------------------------------------
# flags: --repo <name> targets ONE repo (found anywhere on disk via _tess-repos.sh);
# --fleet forces the configured TESS_REPOS fan-out even when inside another repo.
REPO_PICK=""; FORCE_FLEET=0; _args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)  REPO_PICK="${2:-}"; [ -z "$REPO_PICK" ] && { c_red "--repo needs a name"; exit 1; }; shift 2 ;;
    --fleet) FORCE_FLEET=1; shift ;;
    *) _args+=("$1"); shift ;;
  esac
done
set -- ${_args[@]+"${_args[@]}"}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# positional repo form: `tess new <repo> <feature> [base]` — kicks in only when the
# first arg EXACTLY matches a known repo name (see: tess repos). Otherwise the first
# arg is a feature name, exactly as before.
if [ -z "$REPO_PICK" ] && [ "$FORCE_FLEET" -eq 0 ] && [ $# -ge 2 ]; then
  _prc=0
  _pout="$(bash "$SCRIPT_DIR/_tess-repos.sh" pick "$1" 2>/dev/null)" || _prc=$?
  _pname="$(printf '%s' "$_pout" | head -1 | cut -f1 | tr '[:upper:]' '[:lower:]')"
  if { [ "$_prc" -eq 0 ] || [ "$_prc" -eq 3 ]; } && [ "$_pname" = "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" ]; then
    REPO_PICK="$1"; shift
  fi
fi

FEATURE="${1:-}"
BASE="${2:-$DEFAULT_BASE}"   # base branch to cut from (default: main)
[ -z "$FEATURE" ] && { c_red "usage: $0 [--repo <name>|--fleet] [<repo>] <feature-name> [base-branch]"; exit 1; }
check_name "$FEATURE"

# Pick target repos: explicit repo (flag or positional) beats the repo you're
# standing in (when it isn't part of the configured fleet), which beats the
# TESS_REPOS fan-out. Standing inside a fleet repo still fans out the whole
# fleet — same-feature branches across paired repos is the point of the fleet.
TARGETS=()   # "name<TAB>src" pairs
_fleet_targets() {
  if [ "${#REPOS[@]}" -eq 0 ] || [ -z "${REPOS[0]:-}" ]; then
    c_red "no repos configured — run inside a git repo, pass --repo <name>, or set TESS_REPOS in ~/.config/tess/config"
    exit 1
  fi
  for r in "${REPOS[@]}"; do TARGETS+=("$r"$'\t'"$CORE_DIR/$r"); done
}
if [ -n "$REPO_PICK" ]; then
  if [ -d "$REPO_PICK" ] && git -C "$REPO_PICK" rev-parse --git-dir >/dev/null 2>&1; then
    _p="$(cd "$REPO_PICK" && git rev-parse --show-toplevel)"   # --repo <path> form
    c_blue "(repo: $_p)"
    TARGETS+=("$(basename "$_p")"$'\t'"$_p")
  else
    _prc=0
    _pout="$(bash "$SCRIPT_DIR/_tess-repos.sh" pick "$REPO_PICK" 2>/dev/null)" || _prc=$?
    if [ "$_prc" -eq 1 ] || [ -z "$_pout" ]; then
      c_red "no repo matching '$REPO_PICK' — see: tess repos"; exit 1
    elif [ "$_prc" -eq 3 ] && [ -t 0 ] && command -v fzf >/dev/null 2>&1; then
      sel="$(printf '%s\n' "$_pout" | fzf --prompt 'repo ▸ ' --delimiter '\t')" || true
      [ -z "${sel:-}" ] && exit 0
      TARGETS+=("$sel")
    elif [ "$_prc" -eq 3 ]; then
      c_red "'$REPO_PICK' matches several repos:"
      printf '%s\n' "$_pout" | sed $'s/\t/  ->  /;s/^/  /' >&2
      c_red "pass the path instead: tess new --repo <path> <feature>"; exit 2
    else
      c_blue "(repo: ${_pout#*$'\t'} — most active match)"
      TARGETS+=("$_pout")
    fi
  fi
elif [ "$FORCE_FLEET" -eq 0 ] && cwd_top="$(git rev-parse --show-toplevel 2>/dev/null)" && [ -n "$cwd_top" ]; then
  cwd_name="$(basename "$cwd_top")"
  in_fleet=0
  for r in ${REPOS[@]+"${REPOS[@]}"}; do [ "$r" = "$cwd_name" ] && in_fleet=1; done
  if [ "$in_fleet" -eq 1 ]; then
    _fleet_targets
  else
    c_blue "(inside '$cwd_name' — targeting this repo; use --fleet for your configured set)"
    TARGETS+=("$cwd_name"$'\t'"$cwd_top")
  fi
else
  _fleet_targets
fi

DEST_ROOT="$WORKTREE_PARENT/$FEATURE"
mkdir -p "$DEST_ROOT"

c_blue "Creating worktrees for feature '$FEATURE'  ->  $DEST_ROOT"
echo

for pair in "${TARGETS[@]}"; do
  repo="${pair%%$'\t'*}"
  src="${pair#*$'\t'}"
  dst="$DEST_ROOT/$repo"
  c_yellow "  $repo"

  # clone from GitHub if a configured fleet repo doesn't exist locally yet
  if [ ! -d "$src" ] && [[ "$src" == "$CORE_DIR/"* ]]; then
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
