#!/usr/bin/env python3
# tess inject <agent> [--timeout N] [--retries N] [--force] -- <text>
#   echo "text" | tess inject <agent>        (stdin works too)
#
# Reliable PTY injection. `hcom term inject --enter` reports success even when
# the agent is busy (screen ready=false) and the keystrokes silently vanish.
# This wrapper: waits until the input box is actually READY, types the text,
# verifies it appeared in the box, submits, then CONFIRMS the turn landed by
# watching the transcript for our prompt — retrying the submit if it didn't.
#
# Exit codes: 0 landed · 1 usage/agent not found · 2 no PTY screen
#             3 timed out waiting for ready · 4 submitted but never confirmed
#             5 agent blocked on approval (use tess approve / --force)
#             6 input box already has text (--force to append anyway)
import json
import os
import subprocess
import sys
import time

HCOM = (os.environ.get("TESS_HCOM") or "hcom").split()


def hcom(*args, timeout=30):
    try:
        return subprocess.run([*HCOM, *args], capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        r = subprocess.CompletedProcess(args, 124)
        r.stdout, r.stderr = "", str(e)
        return r


def term_state(agent):
    r = hcom("term", agent, "--json")
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def last_exchange(agent):
    r = hcom("transcript", agent, "--json", "--last", "1")
    try:
        ex = json.loads(r.stdout)
        return ex[-1] if ex else None
    except ValueError:
        return None


def status_of(agent):
    r = hcom("list", agent, "status")
    return r.stdout.strip() if r.returncode == 0 else None


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
    timeout, retries, force = 180, 3, False
    agent = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--timeout":
            i += 1
            timeout = int(args[i])
        elif a == "--retries":
            i += 1
            retries = int(args[i])
        elif a == "--force":
            force = True
        elif a.startswith("-"):
            die(1, f"unknown flag '{a}' (usage: tess inject <agent> [--timeout N] [--retries N] [--force] -- <text>)")
        elif agent is None:
            agent = a
        else:
            die(1, "one agent at a time (put the message after --)")
        i += 1
    if not agent:
        die(1, "usage: tess inject <agent> [--timeout N] [--retries N] [--force] -- <text>")
    if text is None:
        if sys.stdin.isatty():
            die(1, "no text: pass it after -- or pipe it on stdin")
        text = sys.stdin.read()
    text = " ".join(text.split())  # PTY input is one line; \n would submit early
    if not text:
        die(1, "empty message — nothing to inject")

    st = status_of(agent)
    if st is None:
        die(1, f"no agent named '{agent}' (see: tess agents)")
    if st == "blocked" and not force:
        die(5, f"'{agent}' is BLOCKED on an approval prompt — injecting would answer the "
               f"dialog, not the agent. Use `tess approve {agent}` first (or --force).")

    # 1. wait until the agent can take keystrokes. The PTY `ready` flag is
    #    unreliable inside cmux panes (observed false even when idle), so the
    #    hook-driven status is the gate: listening == idle == safe to type.
    deadline = time.time() + timeout
    state = None
    while time.time() < deadline:
        state = term_state(agent)
        if state is None:
            die(2, f"'{agent}' has no PTY screen (headless/vanilla agent?) — "
                   f"use `tess tell {agent} -- <msg>` instead.")
        st = status_of(agent)
        if st == "blocked" and not force:
            die(5, f"'{agent}' went BLOCKED on an approval prompt while waiting — "
                   f"use `tess approve {agent}` first (or --force).")
        if st in (None, "inactive"):
            die(1, f"'{agent}' died while waiting (status: {st})")
        if state.get("ready") or st == "listening":
            break
        time.sleep(2)
    else:
        tail = "\n  ".join(l for l in (state or {}).get("lines", [])[-5:] if l.strip())
        die(3, f"'{agent}' never became ready within {timeout}s (still busy). Screen tail:\n  {tail}")

    if state.get("input_text", "").strip() and not force:
        die(6, f"'{agent}' already has text in its input box "
               f"({state['input_text'][:60]!r}) — --force to append anyway.")

    before = last_exchange(agent)
    before_pos = before["position"] if before else -1
    probe = text[:40]

    def landed():
        ex = last_exchange(agent)
        if ex and ex["position"] > before_pos and probe in " ".join(ex.get("user", "").split()):
            return ex["position"]
        return None

    # 2. type, and verify the text really appeared in the box (never type twice
    #    in a row without checking — that would duplicate the message)
    for _ in range(retries):
        state = term_state(agent) or {}
        if probe in state.get("input_text", ""):
            break
        hcom("term", "inject", agent, text)
        time.sleep(0.7)
    else:
        state = term_state(agent) or {}
        if probe not in state.get("input_text", ""):
            die(4, f"typed {retries}x but the text never appeared in '{agent}' input box")

    # 3. submit, then confirm the turn actually landed: our prompt must show up
    #    as a NEW transcript exchange (authoritative — not just "keys sent").
    for _ in range(retries):
        hcom("term", "inject", agent, "--enter")
        confirm_by = time.time() + 12
        while time.time() < confirm_by:
            pos = landed()
            if pos is not None:
                print(f"✓ landed on {agent} (transcript #{pos})")
                return
            time.sleep(1.5)
            state = term_state(agent) or {}
            if probe in state.get("input_text", ""):
                break  # enter didn't take — go resubmit
        # box cleared but transcript not seen yet: loop presses enter on an
        # empty box (a no-op in the TUI) and keeps watching the transcript
    pos = landed()
    if pos is not None:
        print(f"✓ landed on {agent} (transcript #{pos})")
        return
    die(4, f"submitted to '{agent}' but could not confirm the turn landed after "
           f"{retries} attempts — check `tess agents` / `hcom term {agent}`")


if __name__ == "__main__":
    main()
