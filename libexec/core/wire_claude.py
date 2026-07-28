#!/usr/bin/env python3
"""Wire the tess hooks into ~/.claude/settings.json (for people not using the tess plugin).

usage: wire_claude.py <tess-home> [--undo]

Adds two hooks:
  PreToolUse(Bash)  -> hooks/guard.py        blocks raw `git worktree`, redirects to `tess new`
  SessionStart      -> hooks/session-start.sh  one-line pointer + the open coding todos

Merges — the user's own hooks are preserved. tess entries are recognised by the script name in
their command, so a re-run updates in place. Also cleans up the older standalone
`tess todo --hook` entry, which session-start.sh now supersedes.
"""
import json
import os
import sys

SETTINGS = os.path.expanduser("~/.claude/settings.json")


def is_ours(cmd):
    cmd = str(cmd or "")
    return ("hooks/guard.py" in cmd or "hooks/session-start.sh" in cmd
            or "tess todo --hook" in cmd)  # legacy entry from older install.sh


def prune(groups):
    """Drop tess hooks from a hook-group list; return (kept, changed)."""
    changed = False
    kept = []
    for g in groups:
        hs = [h for h in g.get("hooks", []) if not is_ours(h.get("command"))]
        if len(hs) != len(g.get("hooks", [])):
            changed = True
        if hs:
            kept.append({**g, "hooks": hs})
        elif not g.get("hooks"):
            kept.append(g)
    return kept, changed


def main():
    args = [a for a in sys.argv[1:] if a and a != "--undo"]
    undo = "--undo" in sys.argv[1:]
    if not args:
        print("usage: wire_claude.py <tess-home> [--undo]", file=sys.stderr)
        return 2
    home = os.path.abspath(args[0])

    try:
        d = json.load(open(SETTINGS)) if os.path.exists(SETTINGS) else {}
    except Exception:
        print("  ! ~/.claude/settings.json isn't valid JSON — skipped, fix it and re-run")
        return 0

    hooks = d.setdefault("hooks", {})
    wanted = {
        "PreToolUse": {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": 'python3 "%s/hooks/guard.py"' % home, "timeout": 5}],
        },
        "SessionStart": {
            "matcher": "startup|resume|clear|compact",
            "hooks": [{"type": "command", "command": 'bash "%s/hooks/session-start.sh"' % home, "timeout": 10}],
        },
    }

    changed = False
    for event, group in wanted.items():
        kept, pruned = prune(hooks.get(event, []))
        changed = changed or pruned
        if not undo:
            kept.append(group)
            changed = True
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    if not hooks:
        d.pop("hooks", None)

    if not changed:
        print("  · Claude Code (already current)")
        return 0

    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    json.dump(d, open(SETTINGS, "w"), indent=2)
    print("  %s Claude Code — ~/.claude/settings.json" % ("✓ unwired" if undo else "✓"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
