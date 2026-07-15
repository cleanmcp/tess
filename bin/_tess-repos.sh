#!/usr/bin/env bash
# Dynamic repo discovery — finds git repos anywhere under $HOME (no config needed),
# resolves a name to a path, and makes an isolated worktree for ANY repo.
#   _tess-repos.sh index                 (re)build the cache
#   _tess-repos.sh find <name>           print matching  name<TAB>path  lines
#   _tess-repos.sh iso <name> [feature]  make/print an isolated worktree path
#   _tess-repos.sh list                  show all known repos
set -uo pipefail
[ -f "$HOME/.config/tess/config" ] && . "$HOME/.config/tess/config"

CACHE="$HOME/.cache/tess/repos.tsv"; mkdir -p "$(dirname "$CACHE")"
DEPTH="${TESS_REPO_DEPTH:-6}"

_roots() {
  echo "$HOME"
  [ -n "${TESS_CORE:-}" ] && echo "$TESS_CORE"
  for d in ${TESS_REPO_DIRS:-}; do echo "$d"; done
}

_index() {
  { for r in $(_roots); do
      [ -d "$r" ] || continue
      find "$r" -maxdepth "$DEPTH" -type d -name .git 2>/dev/null
    done; } | while IFS= read -r g; do
      case "$g" in
        *node_modules*|*/Library/*|*/.Trash/*|*/.cache/*|*Caches*|*"Application Support"*|\
        *.grok*|*.oh-my-zsh*|*marketplace-cache*|*.npm*|*.cargo*|*.rustup*|*/.local/*|*/.codex/*|*/.hermes/*) continue ;;
      esac
      d="${g%/.git}"; printf '%s\t%s\n' "$(basename "$d")" "$d"
    done | sort -u > "$CACHE.tmp" && mv "$CACHE.tmp" "$CACHE"
}

_fresh() {   # rebuild if missing or >1 day old
  [ -s "$CACHE" ] || { _index; return; }
  local now age; now=$(date +%s); age=$(stat -f %m "$CACHE" 2>/dev/null || echo 0)
  [ $((now - age)) -gt 86400 ] && _index || true
}

_find() {    # name -> matching lines (exact basename first, then fuzzy)
  _fresh
  local q="$1"
  awk -F'\t' -v q="$q" 'tolower($1)==tolower(q){print}' "$CACHE"
  awk -F'\t' -v q="$q" 'tolower($1)!=tolower(q) && index(tolower($1),tolower(q)){print}' "$CACHE"
}

case "${1:-list}" in
  index) _index; echo "indexed $(wc -l < "$CACHE" | tr -d ' ') repos" ;;
  list)  _fresh; column -t -s$'\t' "$CACHE" 2>/dev/null || cat "$CACHE" ;;
  find)  shift; _find "$1" ;;

  iso)
    shift; name="${1:-}"; feature="${2:-}"
    [ -z "$name" ] && { echo "usage: iso <repo> [feature]" >&2; exit 1; }
    hits=(); while IFS= read -r _l; do [ -n "$_l" ] && hits+=("$_l"); done < <(_find "$name")  # (mapfile needs bash4; macOS ships 3.2)
    if [ "${#hits[@]}" -eq 0 ]; then
      echo "no repo named '$name' found under \$HOME. (cd near it once, or set TESS_REPO_DIRS)" >&2; exit 1
    elif [ "${#hits[@]}" -gt 1 ] && [ -t 0 ] && command -v fzf >/dev/null 2>&1; then
      sel="$(printf '%s\n' "${hits[@]}" | fzf --prompt 'repo ▸ ' --with-nth 1 --delimiter '\t')"; [ -z "$sel" ] && exit 0
      repo="${sel#*$'\t'}"
    elif [ "${#hits[@]}" -gt 1 ]; then
      echo "ambiguous '$name':" >&2; printf '%s\n' "${hits[@]}" | sed 's/\t/  →  /;s/^/  /' >&2
      echo "use the full name or set TESS_REPO_DIRS to narrow it." >&2; exit 2
    else
      repo="${hits[0]#*$'\t'}"
    fi
    base="$(basename "$repo")"
    # auto-name the feature if none given: base-a, base-b, ...
    parent="$(dirname "$repo")"; wtroot="$parent/${base}-worktrees"
    if [ -z "$feature" ]; then
      for x in a b c d e f g h i j k; do [ -e "$wtroot/${base}-$x" ] || { feature="${base}-$x"; break; }; done
      feature="${feature:-${base}-wt}"
    fi
    dst="$wtroot/$feature"
    if [ ! -d "$dst" ]; then
      git -C "$repo" worktree prune 2>/dev/null || true
      if git -C "$repo" show-ref --verify --quiet "refs/heads/$feature"; then
        git -C "$repo" worktree add -f "$dst" "$feature" >/dev/null 2>&1
      else
        git -C "$repo" worktree add -f "$dst" -b "$feature" >/dev/null 2>&1
      fi
      # carry over untracked env files
      while IFS= read -r -d '' f; do
        rel="${f#"$repo"/}"; mkdir -p "$dst/$(dirname "$rel")"; cp -p "$f" "$dst/$rel"
      done < <(find "$repo" \( -name node_modules -o -name .git -o -name .next -o -name dist -o -name build \) -prune -o \
                 -type f \( -name '.env' -o -name '.env.*' \) ! -name '*.example' ! -name '*.sample' -print0 2>/dev/null)
    fi
    echo "$dst"      # print the worktree path (callers cd into it)
    ;;
esac
