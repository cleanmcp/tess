#!/usr/bin/env python3
"""Merge the tess hooks into ~/.cursor/hooks.json (Cursor's beforeShellExecution guard).

usage: wire_cursor.py <tess-home> [--undo]

Merges — never overwrites. The user's own hooks are preserved; tess entries are identified by
the tess home path in their command, so a re-run updates in place instead of stacking copies.

Schema (verified against Cursor's hooks docs):
  { "version": 1, "hooks": { "beforeShellExecution": [ { "command": "...", "matcher": "..." } ] } }
A hook denies by printing {"permission":"deny","user_message":...,"agent_message":...}.
"""
import json
import os
import sys

HOOKS = os.path.expanduser("~/.cursor/hooks.json")

# matcher keeps the guard off the hot path: it only runs on commands mentioning "worktree"
ENTRIES = {
    "beforeShellExecution": {"command": "{home}/hooks/guard.py", "matcher": "worktree", "timeout": 5},
    "sessionStart": {"command": "{home}/hooks/session-start.sh", "timeout": 10},
}


def main():
    args = [a for a in sys.argv[1:] if a and a != "--undo"]
    undo = "--undo" in sys.argv[1:]
    if not args:
        print("usage: wire_cursor.py <tess-home> [--undo]", file=sys.stderr)
        return 2
    home = os.path.abspath(args[0])

    if os.path.exists(HOOKS):
        try:
            cfg = json.load(open(HOOKS))
        except Exception:
            print("  ! ~/.cursor/hooks.json isn't valid JSON — skipped, fix it and re-run")
            return 0
    else:
        cfg = {"version": 1, "hooks": {}}

    cfg.setdefault("version", 1)
    hooks = cfg.setdefault("hooks", {})
    changed = False

    for event, entry in ENTRIES.items():
        lst = hooks.setdefault(event, [])
        # ours = any entry pointing into this tess checkout (or a previous one)
        mine = [h for h in lst if isinstance(h, dict) and "/hooks/" in str(h.get("command", ""))
                and str(h.get("command", "")).endswith(entry["command"].split("/")[-1])]
        for h in mine:
            lst.remove(h)
            changed = True
        if not undo:
            lst.append({**entry, "command": entry["command"].format(home=home)})
            changed = True
        if not lst:
            hooks.pop(event, None)

    if not changed:
        print("  · Cursor (already current)")
        return 0

    os.makedirs(os.path.dirname(HOOKS), exist_ok=True)
    json.dump(cfg, open(HOOKS, "w"), indent=2)
    print("  %s Cursor — ~/.cursor/hooks.json" % ("✓ unwired" if undo else "✓"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
