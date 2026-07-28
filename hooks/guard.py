#!/usr/bin/env python3
"""tess shell guard — raw `git worktree` mutations are blocked and redirected to `tess new`.

One script, two host formats. It auto-detects which agent invoked it from the payload shape:

  Claude Code  PreToolUse            {"tool_name":"Bash","tool_input":{"command":...}}
               -> {"hookSpecificOutput":{"permissionDecision":"deny",...}}
  Cursor       beforeShellExecution  {"command":...,"hook_event_name":"beforeShellExecution"}
               -> {"permission":"deny","user_message":...,"agent_message":...}

Why block: `git worktree add` skips everything tess layers on top — .env copying, the repo map,
the AGENTS.md orientation file, budgets, and the teardown path. A worktree created behind tess's
back is invisible to `tess wt`, `tess ship`, and `tess done`.

Fails OPEN in every ambiguous case: no tess on PATH, unparseable input, a read-only subcommand,
an unrecognised host format, or an explicit TESS_ALLOW_RAW_GIT=1 bypass. Only add/remove/move
are ever blocked.
"""
import json
import os
import re
import shutil
import sys

# `git worktree list` is read-only and genuinely useful — only mutations are owned by tess.
BLOCKED_SUBS = ("add", "remove", "move")

# a segment counts as a command position only if it starts with optional VAR=val / sudo, then git
SEGMENT_HEAD = re.compile(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:sudo\s+)?git\b")
WORKTREE_CALL = re.compile(r"\bworktree\s+(\w+)")

ADD_FIX = """Use tess instead:
  tess new <feature>              # the repo you're standing in
  tess new <repo> <feature>       # any repo on disk, by name
  tess new <feature> --base <br>  # cut from a branch other than main
then:  cd "$(tess path <feature>)"

tess also copies .env files in, registers the worktree so `tess wt`, `tess ship` and
`tess done` can see it, and writes an AGENTS.md orientation file for multi-repo features."""

RM_FIX = """Use tess instead:
  tess rm <feature>     # tear down a feature's worktrees (branches survive)
  tess clean            # prune stale registrations
  tess done <feature>   # full teardown: agents + panes + worktrees"""

REASON = """Blocked by tess: `git worktree {sub}` bypasses tess, which owns worktrees in this setup.

{fix}

Run `tess help new` for the full grammar. If you genuinely need raw git here, prefix the
command with TESS_ALLOW_RAW_GIT=1."""


def emit(obj):
    if obj is not None:
        json.dump(obj, sys.stdout)
    sys.exit(0)


def segments(cmd):
    """Split a shell line into command positions on ; && || | and newlines."""
    return re.split(r"(?:\|\||&&|[;\n|])", cmd)


def blocked_sub(cmd):
    """Return the blocked worktree subcommand in `cmd`, or None."""
    if "worktree" not in cmd or "TESS_ALLOW_RAW_GIT=1" in cmd:
        return None
    for seg in segments(cmd):
        if not SEGMENT_HEAD.match(seg):
            continue
        m = WORKTREE_CALL.search(seg)
        if m and m.group(1) in BLOCKED_SUBS:
            return m.group(1)
    return None


def main():
    # bypass: exported in the environment, or set inline on the command itself
    if os.environ.get("TESS_ALLOW_RAW_GIT") == "1":
        emit(None)
    # no tess installed → this plugin must never break plain git
    if not shutil.which("tess"):
        emit(None)

    try:
        payload = json.load(sys.stdin)
    except Exception:
        emit(None)

    # --- host detection -----------------------------------------------------
    if "tool_name" in payload:  # Claude Code PreToolUse
        if payload.get("tool_name") != "Bash":
            emit(None)
        cmd = (payload.get("tool_input") or {}).get("command") or ""
        host = "claude"
    elif isinstance(payload.get("command"), str):  # Cursor beforeShellExecution
        cmd = payload["command"]
        host = "cursor"
    else:
        emit(None)

    # Least privilege: on the allow path emit NOTHING and exit 0, so the host falls back to its
    # own permission rules. Returning {"permission":"allow"} would make this guard grant approval
    # for every command it sees — including ones it knows nothing about.
    sub = blocked_sub(cmd)
    if not sub:
        emit(None)

    reason = REASON.format(sub=sub, fix=ADD_FIX if sub == "add" else RM_FIX)

    if host == "cursor":
        emit(
            {
                "permission": "deny",
                "user_message": "tess blocked `git worktree %s` — use `tess new` instead." % sub,
                "agent_message": reason,
            }
        )
    emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


if __name__ == "__main__":
    main()
