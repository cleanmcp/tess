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
chmod +x "$HERE/bin/tess" "$HERE"/libexec/*/*
ln -sf "$HERE/bin/tess" "$BIN/tess"
# only `tess` goes on PATH — helpers live in <repo>/libexec. Clean up helper
# symlinks left behind by the old flat-bin layout.
for l in "$BIN"/_tess-* "$BIN"/_tess_* "$BIN"/wt "$BIN"/worktree.sh; do
  [ -L "$l" ] || continue
  case "$(readlink "$l")" in "$HERE"/*) rm -f "$l"; echo "  removed stale link: ${l/#$HOME/~}" ;; esac
done

say "› scaffolding config in ~/.config/tess"
mkdir -p "$HOME/.config/tess"
[ -f "$HOME/.config/tess/config" ] || { cp "$HERE/config.example" "$HOME/.config/tess/config"; echo "  created ~/.config/tess/config — edit it to set your vault + repos"; }
[ -f "$HOME/.config/tess/models" ] || printf 'small=llama3.2:1b\nmed=llama3.2:3b\nbig=qwen2.5:7b\n' > "$HOME/.config/tess/models"
mkdir -p "$HOME/.config/tess/commands" "$HOME/.config/tess/templates" "$HOME/.config/tess/state" "$HOME/.config/tess/modes"
[ -f "$HOME/.config/tess/commands/README" ] || echo "Put executable scripts here named '<name>'. Run them as 'tess <name>'. They survive 'git pull' — the repo never touches this folder." > "$HOME/.config/tess/commands/README"
[ -f "$HOME/.config/tess/templates/README" ] || echo "Role templates for 'tess team' (yourname.md -> template: yourname). These override the built-ins in <repo>/templates/." > "$HOME/.config/tess/templates/README"
[ -f "$HOME/.config/tess/modes/README" ] || echo "Agent-mode overrides for tess think/post/boss/read/orchestrate: a think.md / post.md / boss.md / read.md / orchestrate.md here overrides the repo's modes/. The repo copies stay current with 'tess update'; yours win." > "$HOME/.config/tess/modes/README"

say "› teaching every AI agent on this machine about tess"
# Three layers, handled by `tess wire` (re-runnable any time — it's idempotent):
#   skills  → portable SKILL.md linked into every skills root found
#             (Claude Code · Cursor · Codex · Gemini · opencode)
#   hooks   → a guard that blocks raw `git worktree` and redirects to `tess new`,
#             plus the SessionStart todo list (Claude Code + Cursor)
#   primer  → agent-primer.md injected into CLAUDE.md / AGENTS.md / GEMINI.md
bash "$HERE/libexec/core/wire.sh"

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo; echo "  ⚠ add this to your shell rc (~/.zshrc):"; echo "      export PATH=\"\$HOME/.local/bin:\$PATH\"";;
esac

echo
say "core installed. Try:  tess"
echo

[ "$MINIMAL" = "--minimal" ] && exit 0

# ---------- optional, skippable steps ----------
# Everything below is opt-in. The core (worktrees + the agent fleet) already works;
# these add polish and the optional personal "brain/life" extras.
echo "Optional setup (all skippable):"

install_lokus() {
  if [ -d "/Applications/Lokus.app" ]; then echo "  Lokus already installed."; return; fi
  if [ "$(uname -m)" != "arm64" ]; then
    echo "  no Apple-Silicon build detected for your Mac — grab Lokus from https://github.com/lokus-ai/lokus/releases"; return
  fi
  local url tmp vol app
  url="$(curl -fsSL https://api.github.com/repos/lokus-ai/lokus/releases/latest | grep -o 'https://[^"]*aarch64\.dmg' | head -1)"
  [ -z "$url" ] && { echo "  couldn't find the Lokus dmg — see https://github.com/lokus-ai/lokus/releases"; return; }
  tmp="$(mktemp -d)"
  echo "  downloading Lokus…"
  curl -fL --progress-bar "$url" -o "$tmp/Lokus.dmg" || { echo "  download failed"; return; }
  vol="$(hdiutil attach "$tmp/Lokus.dmg" -nobrowse -quiet | grep -o '/Volumes/.*' | tail -1)"
  app="$(find "$vol" -maxdepth 1 -name '*.app' 2>/dev/null | head -1)"
  [ -n "$app" ] && cp -R "$app" /Applications/ && echo "  installed Lokus to /Applications ✓" || echo "  couldn't copy Lokus.app"
  [ -n "$vol" ] && hdiutil detach "$vol" -quiet 2>/dev/null || true
  rm -rf "$tmp"
}

# --- core polish ---
if command -v brew >/dev/null 2>&1; then
  if ask "1. Install nice-to-have CLI tools (fzf zoxide lazygit eza bat ripgrep chafa)?"; then
    brew install fzf zoxide lazygit eza bat ripgrep chafa || true
  fi
else
  echo "  (Homebrew not found — install from https://brew.sh to get the CLI extras)"
fi

if command -v uvx >/dev/null 2>&1 || command -v hcom >/dev/null 2>&1; then
  echo "  ✓ fleet backend reachable (hcom via $(command -v hcom >/dev/null 2>&1 && echo hcom || echo 'uvx hcom')) — tess team/status/ship ready."
else
  echo "  (for the multi-agent fleet, install uv — https://docs.astral.sh/uv — so tess can run 'uvx hcom')"
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

# --- optional personal "brain" (a notes vault) — skip entirely if you don't want it ---
if ask "4. (Optional) Install Lokus, a markdown notes app, for the personal 'brain' features? Any markdown folder works — skip if you won't use tess for notes."; then
  install_lokus
fi

cat <<'PERM'

5. (Optional) Permissions for the macOS "life" features — do these yourself in System Settings.
   Skip all of this if you only want the core (worktrees + fleet); nothing breaks.
   • Full Disk Access → add your terminal / cmux    (for tess messages, calls, calendar, read)
   • Automation → allow terminal → Messages          (for tess send)
   • Calendars (if prompted)                          (for tess calendar)

Done. Run `tess` to see everything.
Edit ~/.config/tess/config to point at your repos (and, optionally, a notes vault).
PERM
