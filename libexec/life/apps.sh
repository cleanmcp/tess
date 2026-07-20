#!/usr/bin/env bash
# tess apps / open / login / startup — launch apps + control what opens at login.
set -uo pipefail
[ -f "$HOME/.config/tess/config" ] && . "$HOME/.config/tess/config"
mode="${1:-apps}"; shift 2>/dev/null || true

_apps() { find /Applications /System/Applications "$HOME/Applications" -maxdepth 2 -name "*.app" 2>/dev/null | sed 's#.*/##;s/\.app$//' | sort -u; }
_li()   { osascript -e 'tell application "System Events" to get the name of every login item' 2>/dev/null | sed 's/, /\n/g; s/^ *//'; }

case "$mode" in
  open|app|launch)
    q="$*"
    a="$(_apps | grep -ix "$q" | head -1)"; [ -z "$a" ] && a="$(_apps | grep -i "$q" | head -1)"
    [ -z "$a" ] && { echo "no app matching '$q'"; exit 1; }
    open -a "$a" && echo "▶ opened $a" ;;

  apps|ls)
    if [ -t 1 ] && command -v fzf >/dev/null 2>&1; then
      a="$(_apps | fzf --prompt 'open ▸ ' --height 60% --reverse)"; [ -n "$a" ] && open -a "$a" && echo "▶ $a"
    else _apps; fi ;;

  login)
    case "${1:-list}" in
      list|"") echo "🚀 opens at login:"; _li | sed 's/^/  /'
               echo "  remove one:  tess login rm \"<name>\"   ·   add:  tess login add \"<App>\"" ;;
      rm|remove) shift; for n in "$@"; do
          osascript -e "tell application \"System Events\" to delete login item \"$n\"" 2>/dev/null \
            && echo "✓ removed '$n' from login" || echo "✗ couldn't remove '$n'"; done ;;
      add) shift; osascript -e "tell application \"System Events\" to make login item at end with properties {path:\"/Applications/$1.app\", hidden:false}" 2>/dev/null \
            && echo "✓ '$1' will open at login" || echo "✗ couldn't add '$1'" ;;
    esac ;;

  startup)
    case "${1:-run}" in
      run|"")
        for a in ${TESS_STARTUP_QUIT:-}; do osascript -e "tell application \"$a\" to quit" 2>/dev/null && echo "✗ quit $a"; done
        if [ -z "${TESS_STARTUP_OPEN:-}" ]; then
          echo "nothing configured — set TESS_STARTUP_OPEN in ~/.config/tess/config"
        fi
        for a in ${TESS_STARTUP_OPEN:-}; do open -a "$a" 2>/dev/null && echo "▶ $a"; done ;;
      install)
        p="$HOME/Library/LaunchAgents/com.tess.startup.plist"; mkdir -p "$(dirname "$p")"
        cat > "$p" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.tess.startup</string>
  <key>ProgramArguments</key><array>
    <string>/bin/sh</string><string>-c</string>
    <string>sleep 8; "$HOME/.local/bin/tess" startup run</string>
  </array>
  <key>RunAtLoad</key><true/>
</dict></plist>
PL
        launchctl unload "$p" 2>/dev/null || true; launchctl load "$p" 2>/dev/null || true
        echo "✓ installed — your startup set (\${TESS_STARTUP_OPEN}) opens at login."
        echo "  edit TESS_STARTUP_OPEN / TESS_STARTUP_QUIT in ~/.config/tess/config" ;;
      uninstall)
        p="$HOME/Library/LaunchAgents/com.tess.startup.plist"
        launchctl unload "$p" 2>/dev/null || true; rm -f "$p"; echo "✓ startup agent removed" ;;
    esac ;;

  *) echo "usage: tess {open <app>|apps|login [list|rm|add]|startup [run|install|uninstall]}" ;;
esac
