#!/usr/bin/env bash
# tess loop <claude|kimi> "<goal>" [max-rounds]
# Autonomous manager→worker loop: a "manager" agent plays YOU — it reviews the
# worker's last report and issues the next instruction, until the goal is DONE.
# The worker runs headless WITH tools and skipped permissions. Runs in the CWD.
set -uo pipefail

agent="${1:-claude}"; shift 2>/dev/null || true
goal="${1:-}"; shift 2>/dev/null || true
max="${1:-10}"
[ -z "$goal" ] && { echo "usage: tess loop <claude|kimi> \"<goal>\" [max-rounds]"; exit 1; }

case "$agent" in
  claude)
    MGR() { claude -p "$1" 2>/dev/null; }
    WRK() { local i="$1" c="${2:-}"; claude -p --dangerously-skip-permissions ${c:+--continue} "$i" 2>/dev/null; } ;;
  kimi)
    MGR() { kimi -p "$1" 2>/dev/null; }
    WRK() { local i="$1" c="${2:-}"; kimi -p -y ${c:+-c} "$i" 2>/dev/null; } ;;
  *) echo "agent must be 'claude' or 'kimi'"; exit 1 ;;
esac

C=$'\033[36m'; Y=$'\033[33m'; G=$'\033[32m'; B=$'\033[1m'; D=$'\033[2m'; R=$'\033[0m'; [ -t 1 ] || { C=; Y=; G=; B=; D=; R=; }
logdir="$HOME/.local/share/tess-loop"; mkdir -p "$logdir"
log="$logdir/$(date +%Y%m%d-%H%M%S).log"

echo "${B}${Y}⚠ autonomous $agent loop${R} — it directs itself and edits files with permissions skipped."
echo "${D}goal:${R} $goal"
echo "${D}dir:${R} $(pwd)   ${D}max rounds:${R} $max   ${D}log:${R} ${log/#$HOME/~}"
echo "${D}Ctrl+C to stop.${R}"
[ -t 0 ] && { printf "${B}start? [y/N] ${R}"; read -r a; [[ "$a" =~ ^[Yy]$ ]] || { echo "aborted."; exit 0; }; }

last="(this is the very start — nothing has been done yet)"
cont=""
for i in $(seq 1 "$max"); do
  echo; echo "${B}══ round $i/$max ══${R}"
  mp="You are the human owner directing an AI worker toward a GOAL. Review the worker's last report and reply with ONLY the next single, concrete instruction (imperative, one message) — or the exact word DONE if the goal is fully achieved and verified. Be specific, one step at a time, and if the worker hit an error tell it how to fix it. Do NOT do the work yourself; direct.

GOAL: $goal

Worker's last report:
$last

Your reply:"
  next="$(MGR "$mp")"
  echo "${C}🧠 you →${R} $next"
  { echo "== round $i =="; echo "MANAGER: $next"; } >> "$log"
  if printf '%s' "$next" | grep -qiE '(^|[^a-zA-Z])DONE([^a-zA-Z]|$)'; then
    echo "${G}✅ goal reached in $i round(s).${R}"; break
  fi
  echo "${D}🤖 worker working…${R}"
  work="$(WRK "$next" "$cont")"; cont=1
  last="$work"
  echo "${Y}🤖 worker →${R} $(printf '%s' "$work" | tail -c 600)"
  echo "WORKER: $work" >> "$log"
done
echo; echo "${D}full transcript: ${log/#$HOME/~}${R}"
