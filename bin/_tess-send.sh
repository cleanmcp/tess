#!/usr/bin/env bash
# tess send <name-or-number> -- <message>   (one-shot; agent-friendly)
# tess send <name>                           (human: picks contact + asks for message)
# Non-interactive (agent/pipe): never prompts — errors with guidance instead.
set -uo pipefail

name=""; msg=""; seen=0
for a in "$@"; do
  if [ "$a" = "--" ]; then seen=1; continue; fi
  if [ "$seen" -eq 0 ]; then name="${name:+$name }$a"; else msg="${msg:+$msg }$a"; fi
done
if [ -z "$name" ]; then
  echo "usage: tess send <name-or-number> -- <message>"; exit 1
fi

matches="$(N="$name" python3 -c "
import os,sys; sys.path.insert(0,os.path.expanduser('~/.local/bin'))
from _tess_common import find_contacts, find_number
q=os.environ['N']; c=find_contacts(q)
if c:
    for n,num in c: print(n+'\t'+num)
else:
    n=find_number(q)
    if n: print(q+'\t'+n)
" 2>/dev/null)"

count="$(printf '%s\n' "$matches" | grep -c . || true)"
if [ "${count:-0}" -eq 0 ]; then echo "no contact/number found for '$name'"; exit 1; fi

if [ "$count" -eq 1 ]; then
  chosen="$matches"
elif [ -t 0 ]; then                       # human present -> picker
  echo "multiple matches for '$name':"
  printf '%s\n' "$matches" | awk -F'\t' '{printf "  %d. %s  (%s)\n", NR, $1, $2}'
  printf "pick #: "; IFS= read -r pick
  case "$pick" in ''|*[!0-9]*) echo "cancelled."; exit 0 ;; esac
  chosen="$(printf '%s\n' "$matches" | sed -n "${pick}p")"
  [ -z "$chosen" ] && { echo "cancelled."; exit 0; }
else                                       # agent -> don't hang, tell it how to disambiguate
  echo "ambiguous: '$name' matches multiple contacts:"
  printf '%s\n' "$matches" | awk -F'\t' '{printf "  - %s (%s)\n", $1, $2}'
  echo "re-run with the FULL name or a number, e.g.  tess send \"$(printf '%s' "$matches" | head -1 | cut -f1)\" -- <message>"
  exit 2
fi
who="${chosen%%$'\t'*}"; num="${chosen##*$'\t'}"

if [ -z "$msg" ]; then
  if [ -t 0 ]; then
    printf "✉️  message to %s: " "$who"; IFS= read -r msg
  else
    echo "no message — pass it inline:  tess send \"$who\" -- <message>"; exit 2
  fi
fi
if [ -z "$msg" ]; then echo "no message — nothing sent."; exit 0; fi

echo "→ $who ($num): $msg"
if MSG="$msg" NUM="$num" osascript -e 'tell application "Messages"
    set svc to 1st service whose service type is iMessage
    send (system attribute "MSG") to buddy (system attribute "NUM") of svc
end tell' 2>/dev/null; then
  echo "✓ sent"
else
  echo "✗ failed — allow Automation (cmux → Messages) in System Settings → Privacy & Security → Automation."
fi
