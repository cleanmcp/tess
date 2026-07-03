#!/usr/bin/env bash
# tess music [now|play|pause|next|prev|stop|<search>]  — control Apple Music
# First use prompts for Automation (terminal → Music).
set -uo pipefail
M() { osascript -e "tell application \"Music\" to $1" 2>/dev/null; }
np() { local n a; n="$(M 'name of current track')"; a="$(M 'artist of current track')"; [ -n "$n" ] && echo "$n — $a" || echo "(unknown track)"; }

cmd="${1:-now}"; shift 2>/dev/null || true
case "$cmd" in
  now|"" )
    st="$(M 'player state')"
    case "$st" in playing) echo "▶ $(np)";; paused) echo "⏸ $(np)";; *) echo "nothing playing";; esac ;;
  play|pause|p|toggle) M 'playpause' >/dev/null; sleep 0.2; echo "$(M 'player state' | sed 's/playing/▶/;s/paused/⏸/') $(np)" ;;
  next|n|skip)  M 'next track' >/dev/null; sleep 0.3; echo "→ $(np)" ;;
  prev|back|b)  M 'previous track' >/dev/null; sleep 0.3; echo "← $(np)" ;;
  stop)         M 'stop' >/dev/null; echo "■ stopped" ;;
  love|like)    M 'set loved of current track to true' >/dev/null; echo "♥ loved: $(np)" ;;
  *)  # play a playlist or a track by name from your library
    q="$cmd $*"; q="${q% }"
    if osascript -e "tell application \"Music\" to play playlist \"$q\"" 2>/dev/null; then
      echo "▶ playlist: $q"
    elif osascript -e "tell application \"Music\"
        set t to (every track whose name contains \"$q\")
        if (count of t) > 0 then play (item 1 of t)
      end tell" 2>/dev/null; then
      sleep 0.3; echo "▶ $(np)"
    else
      echo "couldn't find '$q' as a playlist or track in your library"
    fi ;;
esac
