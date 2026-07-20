#!/usr/bin/env bash
# tess listen — hands-free. Say "tess, <what you want>" out loud; it routes + speaks back.
# Fully offline: sox records a phrase (silence-gated), whisper.cpp transcribes, the
# tess router handles it. Opt-in (CPU/battery), so run it when you want hands-free.
set -uo pipefail

MODEL="${TESS_WHISPER_MODEL:-$HOME/.local/share/whisper/ggml-base.en.bin}"
WCLI="$(command -v whisper-cli || true)"
[ -x "$WCLI" ] || { echo "whisper-cli missing — brew install whisper-cpp"; exit 1; }
[ -f "$MODEL" ] || { echo "whisper model missing: $MODEL"; exit 1; }
command -v rec >/dev/null 2>&1 || { echo "sox missing — brew install sox"; exit 1; }

export TESS_SPEAK_SYNC=1      # TTS finishes before we listen again (no self-echo loop)
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

echo "🎙  tess is listening — say:  \"tess, <what you want>\"   (Ctrl+C to stop)"
echo "    (first time: allow Microphone for your terminal if macOS asks)"
while true; do
  # wait for speech, capture the phrase: start on sound, stop after ~1.5s silence, cap 10s.
  # Record at the mic's native rate, THEN resample to 16k (whisper requires 16k mono).
  rec -q -c 1 -b 16 "$tmp/raw.wav" silence 1 0.1 3% 1 1.5 3% trim 0 10 >/dev/null 2>&1 || { sleep 0.3; continue; }
  [ -s "$tmp/raw.wav" ] || continue
  sox "$tmp/raw.wav" -r 16000 -c 1 "$tmp/c.wav" >/dev/null 2>&1 || continue
  text="$("$WCLI" -m "$MODEL" -f "$tmp/c.wav" -nt -np 2>/dev/null | tr '\n' ' ' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [ -z "$text" ] && continue
  low="$(printf '%s' "$text" | tr '[:upper:]' '[:lower:]')"
  case "$low" in
    *tess*|*tes,*|*tessa*|"hey test"*|*" test "*)
      # strip everything up to & including the wake word
      cmd="$(printf '%s' "$text" | sed -E 's/.*([Tt]ess[a]?|[Tt]est)[[:punct:]]*[[:space:]]*//')"
      [ -z "$cmd" ] && { echo "(heard the wake word, nothing after)"; continue; }
      echo "❯ $cmd"
      python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ask.py" "$cmd"
      ;;
    *) : ;;  # no wake word → ignore
  esac
done
