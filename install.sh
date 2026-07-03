#!/usr/bin/env bash
# tess installer — core install + optional (skippable) setup steps.
#   ./install.sh            interactive
#   ./install.sh --minimal  core only, no prompts
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
MINIMAL="${1:-}"

say() { printf "\033[36m%s\033[0m\n" "$*"; }
ask() { [ "$MINIMAL" = "--minimal" ] && return 1; printf "\033[1m%s\033[0m [y/N] " "$*"; read -r a; [[ "$a" =~ ^[Yy]$ ]]; }

[ "$(uname)" = "Darwin" ] || { echo "tess targets macOS. Some features won't work elsewhere."; }

say "› installing tess into $BIN"
mkdir -p "$BIN"
for f in "$HERE"/bin/*; do chmod +x "$f"; ln -sf "$f" "$BIN/$(basename "$f")"; done

say "› installing agent modes into ~/.claude/modes"
mkdir -p "$HOME/.claude/modes"
cp "$HERE"/modes/*.md "$HOME/.claude/modes/"

say "› scaffolding config in ~/.config/tess"
mkdir -p "$HOME/.config/tess"
[ -f "$HOME/.config/tess/config" ] || { cp "$HERE/config.example" "$HOME/.config/tess/config"; echo "  created ~/.config/tess/config — edit it to set your vault + repos"; }
[ -f "$HOME/.config/tess/models" ] || printf 'small=llama3.2:1b\nmed=llama3.2:3b\nbig=qwen2.5:7b\n' > "$HOME/.config/tess/models"

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo; echo "  ⚠ add this to your shell rc (~/.zshrc):"; echo "      export PATH=\"\$HOME/.local/bin:\$PATH\"";;
esac

echo
say "core installed. Try:  tess"
echo

[ "$MINIMAL" = "--minimal" ] && exit 0

# ---------- optional, skippable steps ----------
echo "Optional setup (all skippable):"

if command -v brew >/dev/null 2>&1; then
  if ask "1. Install nice-to-have CLI tools (fzf zoxide lazygit eza bat ripgrep chafa)?"; then
    brew install fzf zoxide lazygit eza bat ripgrep chafa || true
  fi
else
  echo "  (Homebrew not found — install from https://brew.sh to get the CLI extras)"
fi

if ask "2. Set up OFFLINE local AI (ollama + a small model, ~2GB)? Needed for tess local/ask/voice."; then
  command -v ollama >/dev/null 2>&1 || brew install ollama || true
  brew services start ollama >/dev/null 2>&1 || (ollama serve >/dev/null 2>&1 &)
  sleep 2
  ollama pull llama3.2:3b || true
  echo "  pulled llama3.2:3b. For bigger/smaller: ollama pull qwen2.5:7b / llama3.2:1b"
fi

if ask "3. Set up hands-free voice (whisper.cpp + sox + a speech model, ~150MB)? For tess listen."; then
  brew install whisper-cpp sox || true
  mkdir -p "$HOME/.local/share/whisper"
  [ -f "$HOME/.local/share/whisper/ggml-base.en.bin" ] || \
    curl -fL --progress-bar https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin \
      -o "$HOME/.local/share/whisper/ggml-base.en.bin"
fi

cat <<'PERM'

4. Permissions (do these yourself in System Settings — required for the "life" features):
   • Full Disk Access → add your terminal / cmux    (for tess messages, calls, calendar, read)
   • Automation → allow terminal → Messages          (for tess send)
   • Calendars (if prompted)                          (for tess calendar)
   Skip if you don't want tess touching messages/calendar.

Done. Run `tess` to see everything. Edit ~/.config/tess/config to point at your vault + repos.
PERM
