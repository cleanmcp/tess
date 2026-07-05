#!/usr/bin/env python3
# tess inject <agent> [--timeout N] [--retries N] [--force] [--raw [--expect S]] -- <text>
#   echo "text" | tess inject <agent>        (stdin works too)
#
# Reliable PTY injection. `hcom term inject --enter` reports success even when
# the agent is busy and the keystrokes silently vanish. This wrapper waits
# until the agent is actually idle (hook status), types, verifies the text
# appeared, submits, then CONFIRMS the turn landed via the transcript —
# retrying the submit if it didn't. --raw is for slash commands (/model, ...)
# which never reach the transcript: confirmation is box-cleared (+ --expect
# substring on screen when given).
#
# Exit codes: 0 landed · 1 usage/agent not found · 2 no PTY screen
#             3 timed out waiting for ready · 4 submitted but never confirmed
#             5 agent blocked on approval (use tess approve / --force)
#             6 input box already has text (--force to append anyway)
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _tess_agents import AgentError, inject


def die(code, msg):
    print(f"tess inject: {msg}", file=sys.stderr)
    sys.exit(code)


def main():
    args = sys.argv[1:]
    text = None
    if "--" in args:
        i = args.index("--")
        text = " ".join(args[i + 1:])
        args = args[:i]
    timeout, retries = 180, 3
    force = raw = False
    expect = agent = None

    def val(i):
        if i + 1 >= len(args):
            die(1, f"{args[i]} needs a value")
        return args[i + 1]

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--timeout":
            timeout = int(val(i))
            i += 1
        elif a == "--retries":
            retries = int(val(i))
            i += 1
        elif a == "--expect":
            expect = val(i)
            i += 1
        elif a == "--force":
            force = True
        elif a == "--raw":
            raw = True
        elif a.startswith("-"):
            die(1, f"unknown flag '{a}' (usage: tess inject <agent> [--timeout N] "
                   f"[--retries N] [--force] [--raw [--expect S]] -- <text>)")
        elif agent is None:
            agent = a
        else:
            die(1, "one agent at a time (put the message after --)")
        i += 1
    if not agent:
        die(1, "usage: tess inject <agent> [--timeout N] [--retries N] [--force] "
               "[--raw [--expect S]] -- <text>")
    if text is None:
        if sys.stdin.isatty():
            die(1, "no text: pass it after -- or pipe it on stdin")
        text = sys.stdin.read()
    try:
        print(inject(agent, text, timeout=timeout, retries=retries, force=force,
                     raw=raw, expect=expect))
    except AgentError as e:
        die(e.code, e.msg)


if __name__ == "__main__":
    main()
