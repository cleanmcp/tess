#!/usr/bin/env bash
# tess todo — a persistent, per-machine CODING checklist.
#
# Why: agent sessions are ephemeral; work spans many of them. This is the shared
# checkbox list so any new session (human or agent) picks up where the last left off.
# It is surfaced automatically at the top of every new agent session via a
# SessionStart hook that runs `tess todo --hook` (wired by install.sh).
#
# Storage: ~/.config/tess/state/todos.md — plain markdown checkboxes.
#   • survives `git pull` (lives in config, the repo never touches it)
#   • hand-editable; the file itself is a valid todo list
#   • one todo per line:  - [ ] (id) text  ·  #project  ·  YYYY-MM-DD
set -uo pipefail

STATE_DIR="${TESS_STATE:-$HOME/.config/tess/state}"
FILE="$STATE_DIR/todos.md"
mkdir -p "$STATE_DIR"
[ -f "$FILE" ] || printf '# tess coding todos\n#\n# - [ ] (id) task  ·  #project  ·  date   ·  managed by `tess todo`\n\n' > "$FILE"

if [ -t 1 ]; then
  B=$'\033[1m'; D=$'\033[2m'; R=$'\033[0m'; C=$'\033[36m'; G=$'\033[32m'; Y=$'\033[33m'; M=$'\033[35m'
else
  B=; D=; R=; C=; G=; Y=; M=
fi

# in-place sed: BSD sed wants -i '' , GNU sed wants bare -i
if sed --version >/dev/null 2>&1; then _sedi() { sed -i "$@"; }; else _sedi() { sed -i '' "$@"; }; fi

# current project tag: the git repo name if we're in one, else the cwd name
_project() {
  local top; top="$(git rev-parse --show-toplevel 2>/dev/null)" && { basename "$top"; return; }
  basename "$PWD"
}

# a short, stable, collision-free id (3 hex chars)
_newid() {
  local id
  while :; do
    id=$(printf '%03x' $((RANDOM % 4096)))
    grep -q "($id)" "$FILE" 2>/dev/null || { printf '%s' "$id"; return; }
  done
}

# ids are exactly 3 hex chars — gate BEFORE any id reaches a sed/grep pattern,
# so a regex-shaped argument ('.*') can never match or rewrite every line
_validid() { case "${1:-}" in [0-9a-f][0-9a-f][0-9a-f]) return 0 ;; *) return 1 ;; esac; }
_has() { _validid "$1" && grep -q "^- \[.\] ($1)" "$FILE" 2>/dev/null; }
_count() { local n; n=$(grep -c "$1" "$FILE" 2>/dev/null); printf '%s' "${n:-0}"; }

# parse a raw line into: BOX ID TEXT PROJ DATE (globals)
_parse() {
  local line="$1" body after rest
  BOX="${line:3:1}"                       # ' ', 'x', or '/' (in progress)
  body="${line#*] }"                      # (id) text  ·  #proj  ·  date
  ID="${body#\(}"; ID="${ID%%\)*}"
  after="${body#*\) }"
  TEXT="${after%%  ·  #*}"
  if [ "$TEXT" = "$after" ]; then PROJ=""; DATE=""; else
    rest="${after#*  ·  #}"; PROJ="${rest%%  ·  *}"; DATE="${rest##*  ·  }"
  fi
}

_render() {  # $1 = raw line, $2 = plain|tty
  _parse "$1"
  local mark tag
  case "$BOX" in x) mark="☑" ;; /) mark="◐" ;; *) mark="☐" ;; esac
  [ -n "$PROJ" ] && tag="  ${D}#${PROJ}${R}" || tag=""
  if [ "$2" = "plain" ]; then
    printf '  %s (%s) %s%s\n' "$mark" "$ID" "$TEXT" "${PROJ:+  [$PROJ]}"
  elif [ "$BOX" = "x" ]; then
    printf '  %s%s %s(%s)%s %s%s\n' "$D" "$mark" "$D" "$ID" "$R$D" "$TEXT" "$R"
  elif [ "$BOX" = "/" ]; then
    printf '  %s%s%s %s(%s)%s %s%s\n' "$Y" "$mark" "$R" "$D" "$ID" "$R" "$TEXT" "$tag"
  else
    printf '  %s%s%s %s(%s)%s %s%s\n' "$G" "$mark" "$R" "$D" "$ID" "$R" "$TEXT" "$tag"
  fi
}

_add() {
  local proj=""
  case "${1:-}" in -p|--project) proj="${2:-}"; shift 2 ;; esac
  local text="$*"
  [ -n "${text// }" ] || { echo "usage: tess todo add [-p <project>] <text>"; return 2; }
  local id date
  id="$(_newid)"; [ -n "$proj" ] || proj="$(_project)"; date="$(date +%Y-%m-%d)"
  printf -- '- [ ] (%s) %s  ·  #%s  ·  %s\n' "$id" "$text" "$proj" "$date" >> "$FILE"
  printf '%sadded%s %s(%s)%s %s  %s#%s%s\n' "$G" "$R" "$D" "$id" "$R" "$text" "$D" "$proj" "$R"
}

_setbox() {  # $1=id $2=' '|x
  _has "$1" || { echo "no todo ($1)"; return 1; }
  _sedi -E "s#^- \[.\] \($1\)#- [$2] ($1)#" "$FILE"
}
_done()   { local ok=1; for id in "$@"; do _setbox "$id" x  && { printf '%s✓%s done (%s)\n' "$G" "$R" "$id"; ok=0; }; done; return $ok; }
_start()  { [ $# -gt 0 ] || { echo "usage: tess todo start <id…>"; return 2; }; local ok=1; for id in "$@"; do _setbox "$id" / && { printf '%s◐%s started (%s)\n' "$Y" "$R" "$id"; ok=0; }; done; return $ok; }
_reopen() { for id in "$@"; do _setbox "$id" ' ' && printf 'reopened (%s)\n' "$id"; done; }
_rm()     { for id in "$@"; do _has "$id" && { _sedi -E "/^- \[.\] \($id\)/d" "$FILE"; echo "removed ($id)"; } || echo "no todo ($id)"; done; }
_clear()  { local n; n=$(_count '^- \[x\]'); _sedi -E '/^- \[x\] /d' "$FILE"; echo "cleared $n completed"; }

_list() {  # $1 = "all" to include completed
  local open done_
  open=$(_count '^- \[[ /]\]'); done_=$(_count '^- \[x\]')
  printf '\n  %s%stess todos%s %s· %s open · %s done%s\n\n' "$B" "$M" "$R" "$D" "$open" "$done_" "$R"
  if [ "$open" -eq 0 ] && { [ "${1:-}" != "all" ] || [ "$done_" -eq 0 ]; }; then
    printf '  %snothing here — %stess todo add <text>%s\n\n' "$D" "$C" "$R"; return
  fi
  grep '^- \[/\]' "$FILE" 2>/dev/null | while IFS= read -r l; do _render "$l" tty; done
  grep '^- \[ \]' "$FILE" 2>/dev/null | while IFS= read -r l; do _render "$l" tty; done
  if [ "${1:-}" = "all" ] && [ "$done_" -gt 0 ]; then
    printf '\n  %sdone:%s\n' "$D" "$R"
    grep '^- \[x\]' "$FILE" 2>/dev/null | while IFS= read -r l; do _render "$l" tty; done
  fi
  echo
}

# --hook: what a new session sees. Plain, compact, silent when empty. Never errors.
_hook() {
  local open; open=$(_count '^- \[[ /]\]')
  [ "$open" -eq 0 ] && return 0
  echo "Open coding todos (\`tess todo\` to manage · \`tess todo done <id>\` to check off):"
  grep '^- \[[ /]\]' "$FILE" 2>/dev/null | head -15 | while IFS= read -r l; do
    if [ "${l:3:1}" = "/" ]; then o=$(_render "$l" plain); printf '▶ %s\n' "${o#  }"; else _render "$l" plain; fi
  done
  [ "$open" -gt 15 ] && echo "  … and $((open-15)) more"
  return 0
}

_fit() {  # pad/truncate to $w display chars (${#} + ${:0:} are char-aware, not byte)
  local s="$1"
  [ ${#s} -gt "$w" ] && s="${s:0:$((w-1))}…"
  printf '%s%*s' "$s" $(( w - ${#s} )) ""
}

# board: pure view — TO DO / IN PROGRESS / DONE. tty = side-by-side columns,
# piped = stacked plain sections agents can parse. Never mutates the file.
_board() {
  local -a T=() P=() X=()
  local l i dall
  while IFS= read -r l; do T+=("$l"); done < <(grep '^- \[ \]' "$FILE" 2>/dev/null)
  while IFS= read -r l; do P+=("$l"); done < <(grep '^- \[/\]' "$FILE" 2>/dev/null)
  while IFS= read -r l; do X+=("$l"); done < <(grep '^- \[x\]' "$FILE" 2>/dev/null | head -10)
  dall=$(_count '^- \[x\]')
  if [ ${#T[@]} -eq 0 ] && [ ${#P[@]} -eq 0 ] && [ "$dall" -eq 0 ]; then
    printf '  %snothing here — %stess todo add <text>%s\n' "$D" "$C" "$R"; return 0
  fi
  if [ ! -t 1 ]; then
    echo "== to do =="
    for ((i=0; i<${#T[@]}; i++)); do _render "${T[$i]}" plain; done
    echo "== in progress =="
    for ((i=0; i<${#P[@]}; i++)); do _render "${P[$i]}" plain; done
    echo "== done =="
    for ((i=0; i<${#X[@]}; i++)); do _render "${X[$i]}" plain; done
    [ "$dall" -gt 10 ] && echo "  … and $((dall-10)) more"
    return 0
  fi
  local w cols a b c o
  cols=$(tput cols 2>/dev/null || echo 120); w=$(( (cols - 8) / 3 )); [ "$w" -lt 16 ] && w=16
  printf '\n  %s%s%s  %s%s%s  %s%s%s\n' \
    "$B" "$(_fit "TO DO (${#T[@]})")" "$R" \
    "$B" "$(_fit "IN PROGRESS (${#P[@]})")" "$R" \
    "$B" "DONE ($dall)" "$R"
  local n=${#T[@]}; [ ${#P[@]} -gt "$n" ] && n=${#P[@]}; [ ${#X[@]} -gt "$n" ] && n=${#X[@]}
  for ((i=0; i<n; i++)); do
    a=""; b=""; c=""
    [ "$i" -lt ${#T[@]} ] && { o=$(_render "${T[$i]}" plain); a="${o#  }"; }
    [ "$i" -lt ${#P[@]} ] && { o=$(_render "${P[$i]}" plain); b="${o#  }"; }
    [ "$i" -lt ${#X[@]} ] && { o=$(_render "${X[$i]}" plain); c="${o#  }"; }
    if [ -n "$c" ]; then
      printf '  %s  %s  %s%s%s\n' "$(_fit "$a")" "$(_fit "$b")" "$D" "$c" "$R"
    else
      printf '  %s  %s\n' "$(_fit "$a")" "$(_fit "$b")"
    fi
  done
  [ "$dall" -gt 10 ] && printf '  %s  %s  %s… and %s more%s\n' "$(_fit "")" "$(_fit "")" "$D" "$((dall-10))" "$R"
  echo
  return 0
}

_help() {
  cat <<EOF
${B}tess todo${R} — persistent coding checklist (shared across every session)
  ${C}tess todo${R}                list open todos        ${D}(${C}todo all${R} = include done)${R}
  ${C}tess todo add${R} ${D}<text>${R}     add one (auto-tagged with the current repo)
  ${C}tess todo start${R} ${D}<id…>${R}    mark in progress ${D}(shows as ◐)${R}
  ${C}tess todo done${R} ${D}<id…>${R}     check off        ${D}(${C}reopen${R} <id> to un-check)${R}
  ${C}tess todo board${R}          board view: to do / in progress / done
  ${C}tess todo rm${R} ${D}<id…>${R}       delete           ${D}(${C}clear${R} = drop all completed)${R}
  ${C}tess todo edit${R}           open the file in \$EDITOR
  ${D}stored in ~/.config/tess/state/todos.md · shown to new agent sessions automatically${R}
EOF
}

cmd="${1:-list}"; shift || true
case "$cmd" in
  ""|list|ls|show|open)      _list ;;
  all)                       _list all ;;
  add|new|a|+)               _add "$@" ;;
  done|do|check|x|✓|complete) _done "$@" ;;
  start|doing|wip)           _start "$@" ;;
  board|kanban)              _board ;;
  reopen|undone|uncheck)     _reopen "$@" ;;
  rm|del|delete|drop)        _rm "$@" ;;
  clear|clean|prune)         _clear "$@" ;;
  edit|e)                    "${EDITOR:-vi}" "$FILE" ;;
  file|path)                 echo "$FILE" ;;
  --hook|hook)               _hook ;;
  -h|--help|help)            _help ;;
  *)  # `tess todo buy milk` → treat the whole thing as an add
      _add "$cmd" "$@" ;;
esac
