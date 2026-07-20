#!/usr/bin/env bash
# The repo brain — maps every git repo on the machine and ranks them by how much
# you actually use them, so "tess new lokus fix-x" picks the RIGHT lokus.
#   repos.sh index                 (re)build the map now
#   repos.sh list                  ranked repos (most active first)
#   repos.sh find <name>           matching  name<TAB>path  lines, best first
#   repos.sh pick <name>           ONE confident match (exit 3 = ambiguous, candidates on stdout)
#
# Ranking = zoxide frecency (if installed) + git activity (.git/HEAD mtime).
# macOS permission hygiene: NEVER triggers TCC dialogs. Full Disk Access is
# probed silently (reading TCC.db denies without prompting); without FDA the
# promptable folders (Desktop/Documents/Downloads) are skipped, not prompted.
set -uo pipefail
[ -f "$HOME/.config/tess/config" ] && . "$HOME/.config/tess/config"

CACHE="$HOME/.cache/tess/repos.tsv"; mkdir -p "$(dirname "$CACHE")"
DEPTH="${TESS_REPO_DEPTH:-6}"
NOW="$(date +%s)"

_has_fda() {  # silent probe: TCC.db reads never prompt — they just fail without FDA
  head -c1 "$HOME/Library/Application Support/com.apple.TCC/TCC.db" >/dev/null 2>&1
}

_roots() {
  echo "$HOME"
  [ -n "${TESS_CORE:-}" ] && echo "$TESS_CORE"
  for d in ${TESS_REPO_DIRS:-}; do echo "$d"; done
}

_activity() {  # newest of HEAD / index / FETCH_HEAD mtimes — "when did you last touch it"
  local g="$1/.git" m=0 t f
  for f in HEAD index FETCH_HEAD; do
    t="$(stat -f %m "$g/$f" 2>/dev/null || echo 0)"
    [ "$t" -gt "$m" ] && m="$t"
  done
  echo "$m"
}

_zx_scores() {  # zoxide dirs resolved to repo roots: score<TAB>repo-root
  command -v zoxide >/dev/null 2>&1 || return 0
  zoxide query --list --score 2>/dev/null | head -300 | while read -r score dir; do
    [ -d "$dir" ] || continue
    if [ -e "$dir/.git" ]; then
      printf '%s\t%s\n' "${score%%.*}" "$dir"
    else
      top="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)" || continue
      [ -n "$top" ] && printf '%s\t%s\n' "${score%%.*}" "$top"
    fi
  done
}

_index() {
  local skip_tcc=1
  _has_fda && skip_tcc=0
  local zx; zx="$(mktemp)"; _zx_scores | sort -t$'\t' -k2,2 -u > "$zx"
  { for r in $(_roots); do
      [ -d "$r" ] || continue
      find "$r" -maxdepth "$DEPTH" \( -name node_modules -o -name Library -o -name .Trash \) -prune -o \
        -type d -name .git -print 2>/dev/null
    done; } | while IFS= read -r g; do
      case "$g" in
        *node_modules*|*/Library/*|*/.Trash/*|*/.cache/*|*Caches*|*"Application Support"*|\
        *.grok*|*.oh-my-zsh*|*marketplace-cache*|*.npm*|*.cargo*|*.rustup*|*/.local/*|*/.codex/*|*/.hermes/*|*-worktrees/*) continue ;;
      esac
      d="${g%/.git}"
      if [ "$skip_tcc" = 1 ]; then
        case "$d" in "$HOME/Desktop"*|"$HOME/Documents"*|"$HOME/Downloads"*) continue ;; esac
      fi
      act="$(_activity "$d")"
      z="$(awk -F'\t' -v p="$d" '$2==p{print $1; exit}' "$zx")"
      printf '%s\t%s\t%s\t%s\n' "$(basename "$d")" "$d" "$act" "${z:-0}"
    done | sort -u | sort -t$'\t' -k4,4nr -k3,3nr > "$CACHE.tmp" && mv "$CACHE.tmp" "$CACHE"
  rm -f "$zx"
  [ "$skip_tcc" = 1 ] && echo "(no Full Disk Access — skipped Desktop/Documents/Downloads to avoid permission prompts; add dirs via TESS_REPO_DIRS)" >&2
  true
}

_fresh() {   # rebuild if missing or >1 day old
  [ -s "$CACHE" ] || { _index; return; }
  local age; age=$(stat -f %m "$CACHE" 2>/dev/null || echo 0)
  [ $((NOW - age)) -gt 86400 ] && _index || true
}

_find() {    # name -> matching lines (exact basename first, then fuzzy), rank order kept
  _fresh
  local q="$1"
  awk -F'\t' -v q="$q" 'tolower($1)==tolower(q){print $1"\t"$2}' "$CACHE"
  awk -F'\t' -v q="$q" 'tolower($1)!=tolower(q) && index(tolower($1),tolower(q)){print $1"\t"$2}' "$CACHE"
}

_age() {  # epoch -> human
  local s=$((NOW - $1))
  if   [ "$1" -le 0 ]; then echo "-"
  elif [ "$s" -lt 3600 ];  then echo "$((s/60))m"
  elif [ "$s" -lt 86400 ]; then echo "$((s/3600))h"
  else echo "$((s/86400))d"; fi
}

case "${1:-list}" in
  index) _index; echo "indexed $(wc -l < "$CACHE" | tr -d ' ') repos"; _has_fda || true ;;
  list)
    _fresh
    awk -F'\t' '{print $1"\t"$2"\t"$3"\t"$4}' "$CACHE" | while IFS=$'\t' read -r n p a z; do
      printf '%s\t%s\t%s\t%s\n' "$n" "active $(_age "$a")" "$([ "$z" -gt 0 ] 2>/dev/null && echo "z:$z" || echo "")" "$p"
    done | column -t -s$'\t'
    ;;
  find)  shift; _find "${1:?usage: find <name>}" ;;

  pick)  # ONE best match. exit 0 = confident single answer on stdout (name\tpath).
         # exit 3 = ambiguous: candidates on stdout, caller chooses. exit 1 = none.
    shift; q="${1:?usage: pick <name>}"
    _fresh
    hits=(); while IFS= read -r _l; do [ -n "$_l" ] && hits+=("$_l"); done \
      < <(awk -F'\t' -v q="$q" 'tolower($1)==tolower(q){print}' "$CACHE")
    if [ "${#hits[@]}" -eq 0 ]; then
      # no exact basename — a UNIQUE fuzzy match still counts
      while IFS= read -r _l; do [ -n "$_l" ] && hits+=("$_l"); done \
        < <(awk -F'\t' -v q="$q" 'index(tolower($1),tolower(q)){print}' "$CACHE")
      [ "${#hits[@]}" -eq 0 ] && exit 1
      [ "${#hits[@]}" -gt 1 ] && { printf '%s\n' "${hits[@]}" | cut -f1,2; exit 3; }
    fi
    if [ "${#hits[@]}" -eq 1 ]; then echo "${hits[0]}" | cut -f1,2; exit 0; fi
    # several copies of the same name: the one you USE wins — zoxide beats silence,
    # then clearly-newer git activity (7+ days) beats stale clones.
    best="${hits[0]}"; second="${hits[1]}"
    b_act="$(echo "$best" | cut -f3)"; b_z="$(echo "$best" | cut -f4)"
    s_act="$(echo "$second" | cut -f3)"; s_z="$(echo "$second" | cut -f4)"
    if { [ "${b_z:-0}" -gt 0 ] && [ "${s_z:-0}" -eq 0 ]; } || [ $((b_act - s_act)) -gt 604800 ]; then
      echo "$best" | cut -f1,2; exit 0
    fi
    printf '%s\n' "${hits[@]}" | cut -f1,2; exit 3
    ;;

  *) echo "usage: $0 [index|list|find <name>|pick <name>]" >&2; exit 1 ;;
esac
