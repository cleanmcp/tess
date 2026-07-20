#!/usr/bin/env bash
#
# worktree.sh — create matching git worktrees for a feature, one per target repo.
# Untracked env files (.env, .env.local, ...) are copied from each source repo
# into its new worktree, since `git worktree` never carries untracked files.
#
# Usage:
#   worktree.sh <feature>                    # repo you're in; fleet repo/outside -> your TESS_REPOS
#   worktree.sh <repo> <feature>             # ONE repo by name (see: tess repos). Unknown repo = error.
#   worktree.sh --repo <name|path>[,...] <feature>   # explicit repo(s)
#   worktree.sh --fleet|--all <feature>      # force the configured set (TESS_REPOS / TESS_REPOS_ALL)
#   worktree.sh --base <branch> <feature>    # cut from a branch other than main
#   worktree.sh rm <feature>                 # remove the feature's worktrees again
#
# Grammar is deterministic: with two positionals the first is ALWAYS a repo
# name — it is never silently reinterpreted as anything else.
#
# Worktrees land at:  <worktree-root>/<feature>/<repo>
# A single-repo feature is agent-friendly: no orientation shell files; agents
# land straight in the repo (tess path <feature> returns the repo dir).
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
read -r -a REPOS <<< "${TESS_REPOS:-}"          # the configured fleet
DEFAULT_BASE="${TESS_MAIN_BRANCH:-main}"

usage() { sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'; }
case "${1:-}" in -h|--help) usage; exit 0 ;; esac

# --- helpers -----------------------------------------------------------------
c_blue()  { printf "\033[34m%s\033[0m\n" "$*"; }
c_green() { printf "\033[32m%s\033[0m\n" "$*"; }
c_yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
c_red()   { printf "\033[31m%s\033[0m\n" "$*" >&2; }

# a feature name must never be a flag (--help once created a junk worktree) or
# anything path-unsafe — this script is also called directly, so guard here too.
check_name() {
  case "${1:-}" in
    ""  ) return 0 ;;  # caller handles its own "missing name" usage error
    -*  ) c_red "refusing feature name '$1' — looks like a flag. (help: $0 --help)"; exit 2 ;;
    .*|*/*|*[!A-Za-z0-9._-]*) c_red "refusing feature name '$1' — letters, digits, . _ - only"; exit 2 ;;
  esac
}

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
  # features created with --all/--repo or an older config tear down fully too)
  for dst in "$DEST_ROOT"/*/; do
    [ -d "$dst" ] || continue
    repo="$(basename "$dst")"; src="$CORE_DIR/$repo"
    # non-fleet features live outside CORE_DIR — follow the worktree's own pointer
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
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_PICK=""; FORCE_FLEET=0; BASE="$DEFAULT_BASE"; _pos=()
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)  REPO_PICK="${2:-}"; [ -z "$REPO_PICK" ] && { c_red "--repo needs a name or path"; exit 1; }; shift 2 ;;
    --base)  BASE="${2:-}"; [ -z "$BASE" ] && { c_red "--base needs a branch name"; exit 1; }; shift 2 ;;
    --fleet) FORCE_FLEET=1; shift ;;
    --all)   FORCE_FLEET=1; read -r -a _opt <<< "${TESS_REPOS_ALL:-${TESS_REPOS:-}}"; REPOS=("${_opt[@]}"); shift ;;
    --*)     c_red "unknown flag '$1' (help: $0 --help)"; exit 2 ;;
    *) _pos+=("$1"); shift ;;
  esac
done

# positionals: 1 = <feature> · 2 = <repo> <feature>. Never anything else.
FEATURE=""
case "${#_pos[@]}" in
  0) c_red "usage: $0 [--repo <name>|--fleet|--all] [--base <branch>] [<repo>] <feature>"; exit 1 ;;
  1) FEATURE="${_pos[0]}" ;;
  2) if [ -n "$REPO_PICK" ]; then c_red "give the repo either positionally or via --repo, not both"; exit 2; fi
     REPO_PICK="${_pos[0]}"; FEATURE="${_pos[1]}" ;;
  *) c_red "too many arguments — usage: $0 [<repo>] <feature>  (base branch goes via --base <branch>)"; exit 2 ;;
esac
check_name "$FEATURE"

# resolve one repo entry (name or path) -> "name<TAB>src" lines (exits on failure)
resolve_repo() {
  local q="$1" rc out sel
  if [ -d "$q" ] && git -C "$q" rev-parse --git-dir >/dev/null 2>&1; then
    local top; top="$(cd "$q" && git rev-parse --show-toplevel)"
    printf '%s\t%s\n' "$(basename "$top")" "$top"; return 0
  fi
  rc=0; out="$(bash "$SCRIPT_DIR/repos.sh" pick "$q" 2>/dev/null)" || rc=$?
  if [ "$rc" -eq 1 ] || [ -z "$out" ]; then
    c_red "no repo named '$q' — see: tess repos  (rescan: tess repos index)"
    c_red "(meant a feature called '$q' cut from a branch? use: tess new $q --base <branch>)"
    return 1
  elif [ "$rc" -eq 3 ] && [ -t 0 ] && command -v fzf >/dev/null 2>&1; then
    sel="$(printf '%s\n' "$out" | fzf --prompt 'repo ▸ ' --delimiter '\t')" || true
    [ -z "${sel:-}" ] && return 9   # picker cancelled — not an error
    printf '%s\n' "$sel"
  elif [ "$rc" -eq 3 ]; then
    c_red "'$q' matches several repos:"
    printf '%s\n' "$out" | sed $'s/\t/  ->  /;s/^/  /' >&2
    c_red "pass the path instead: tess new --repo <path> $FEATURE"; return 2
  else
    printf '%s\n' "$out"
  fi
}

# Pick target repos, in order of explicitness:
#   --repo / positional repo  >  --fleet/--all  >  the repo you're standing in
#   (a fleet member still fans out the whole fleet — paired branches across the
#   fleet is the point)  >  the configured fleet  >  a clear error.
TARGETS=()   # "name<TAB>src" pairs
_fleet_targets() {
  if [ "${#REPOS[@]}" -eq 0 ] || [ -z "${REPOS[0]:-}" ]; then
    c_red "no repos configured — run inside a git repo, pass --repo <name>, or set TESS_REPOS in ~/.config/tess/config"
    exit 1
  fi
  for r in "${REPOS[@]}"; do TARGETS+=("$r"$'\t'"$CORE_DIR/$r"); done
}
if [ -n "$REPO_PICK" ]; then
  IFS=',' read -r -a _picks <<< "$REPO_PICK"
  for _p in "${_picks[@]}"; do
    [ -z "$_p" ] && continue
    _rrc=0; _out="$(resolve_repo "$_p")" || _rrc=$?
    [ "$_rrc" -eq 9 ] && exit 0            # picker cancelled — clean stop
    [ "$_rrc" -ne 0 ] && exit "$_rrc"      # unknown/ambiguous repo — real error
    while IFS= read -r _l; do [ -n "$_l" ] && TARGETS+=("$_l"); done <<< "$_out"
  done
  [ "${#TARGETS[@]}" -eq 1 ] && c_blue "(repo: ${TARGETS[0]#*$'\t'})"
elif [ "$FORCE_FLEET" -eq 1 ]; then
  _fleet_targets
elif cwd_top="$(git rev-parse --show-toplevel 2>/dev/null)" && [ -n "$cwd_top" ]; then
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

CREATED=()   # repo names that now have a live worktree
for pair in "${TARGETS[@]}"; do
  repo="${pair%%$'\t'*}"
  src="${pair#*$'\t'}"
  dst="$DEST_ROOT/$repo"
  c_yellow "  $repo"

  # a configured fleet repo that isn't on disk yet: clone it from your remote.
  # TESS_GIT_REMOTE is either a full base URL (https://... or git@...) or a
  # bare GitHub org/user name.
  if [ ! -d "$src" ] && [[ "$src" == "$CORE_DIR/"* ]]; then
    if [ -z "${TESS_GIT_REMOTE:-}" ]; then
      c_red "      $repo is not on disk and TESS_GIT_REMOTE is unset — clone it into $CORE_DIR yourself, or set TESS_GIT_REMOTE in ~/.config/tess/config"
      continue
    fi
    case "$TESS_GIT_REMOTE" in
      *://*|*@*) _remote="${TESS_GIT_REMOTE%/}/$repo.git" ;;
      *)         _remote="https://github.com/${TESS_GIT_REMOTE%/}/$repo.git" ;;
    esac
    c_blue "      cloning $_remote ..."
    if ! git clone "$_remote" "$src" >/dev/null 2>&1; then
      c_red "      clone failed ($_remote) — clone it manually, then re-run"
      continue
    fi
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
    CREATED+=("$repo")
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
  CREATED+=("$repo")
  echo
done

if [ "${#CREATED[@]}" -eq 0 ]; then
  rmdir "$DEST_ROOT" 2>/dev/null || true
  c_red "nothing created for '$FEATURE'."
  exit 1
fi

# multi-repo features get an orientation note, because the feature ROOT is not
# a repo (each subfolder is a worktree) and agents launched there need to know.
# single-repo features skip it — agents land straight inside the one repo.
if [ "${#CREATED[@]}" -gt 1 ]; then
  {
    echo "# Feature: $FEATURE"
    echo
    echo "> This folder is **not** a git repo. It holds one isolated **git worktree per repo**."
    echo "> To run git, \`cd\` into a subfolder. Each has a \`.git\` **file** (a worktree pointer) —"
    echo "> that is normal, they ARE git-tracked, on branch \`$FEATURE\`."
    echo
    echo "## Repos here"
    for repo in "${CREATED[@]}"; do
      echo "- \`$repo/\` — branch \`$FEATURE\` (see its own CLAUDE.md)"
    done
    echo
    echo "Only edit inside this feature's worktrees. Source repos live elsewhere (tess wt shows them)."
  } > "$DEST_ROOT/AGENTS.md"
  ln -sf AGENTS.md "$DEST_ROOT/CLAUDE.md"
fi

c_green "Done. Worktrees are in: $DEST_ROOT"
echo "Tear down later with:  tess rm $FEATURE"
