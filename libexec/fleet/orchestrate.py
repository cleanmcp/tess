#!/usr/bin/env python3
# tess orchestrate "<goal>" [--model M] [--effort E] [--dir D] [--dry-run]
# tess orchestrate off
#
# Spawns ONE lead agent wired for command: it gets the orchestrator system
# prompt (modes/orchestrate.md), becomes the registered LEAD (so tess watch
# escalations are DM'd straight into its conversation), and receives the goal.
# 'off' hands the lead role back to @bigboss (you) and leaves agents running.
import functools
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
print = functools.partial(print, flush=True)
from tess_agents import AgentError, inject, launch

LIBEXEC = os.environ.get("TESS_LIB") or os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
MODE = os.path.join(os.path.dirname(LIBEXEC), "modes", "orchestrate.md")
STATE_DIR = os.path.expanduser("~/.config/tess/state")
LEAD_FILE = os.path.join(STATE_DIR, "lead")


def die(msg, code=1):
    print(f"tess orchestrate: {msg}", file=sys.stderr)
    sys.exit(code)


def watch_running():
    try:
        pid = int(open(os.path.join(STATE_DIR, "watch.pid")).read().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def main():
    args = sys.argv[1:]
    if args and args[0] == "off":
        try:
            os.remove(LEAD_FILE)
            print("✓ lead role reset to @bigboss (escalations + inbox are yours again)")
        except OSError:
            print("lead was already @bigboss")
        return

    goal = model = effort = None
    wdir = os.getcwd()
    dry = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--model":
            i += 1
            model = args[i] if i < len(args) else die("--model needs a value")
        elif a == "--effort":
            i += 1
            effort = args[i] if i < len(args) else die("--effort needs a value")
        elif a == "--dir":
            i += 1
            wdir = args[i] if i < len(args) else die("--dir needs a value")
        elif a == "--dry-run":
            dry = True
        elif a.startswith("-"):
            die(f"unknown flag '{a}'")
        elif goal is None:
            goal = a
        else:
            die("quote the goal: tess orchestrate \"<goal>\"")
        i += 1
    if not goal:
        die("usage: tess orchestrate \"<goal>\" [--model M] [--effort E] [--dry-run] | off")
    try:
        mode_text = open(MODE).read()
    except OSError:
        die(f"missing {MODE}")

    goal_msg = (f"GOAL from @bigboss: {goal}\n\n"
                f"Take command. Start by listing your plan of sub-agents (feature → task → "
                f"model), then execute it with tess team / tess claude. Report milestones "
                f"to @bigboss as you go.")
    if dry:
        print(f"would spawn LEAD claude in {wdir} [tag lead]")
        print(f"  system prompt: modes/orchestrate.md ({len(mode_text)} chars)")
        if model:
            print(f"  model: {model} (verified after spawn)")
        if effort:
            print(f"  effort: {effort} (verified after spawn)")
        print(f"  then: register as lead + ensure tess watch on + inject goal "
              f"({len(goal_msg)} chars)")
        return

    print(f"spawning the LEAD in {wdir}…")
    tool_args = ["--append-system-prompt", mode_text]
    if model:
        tool_args += ["--model", model]
    try:
        name = launch("claude", wdir, tag="lead", tool_args=tool_args)
        print(f"  lead: {name}")
        if model:
            inject(name, f"/model {model}", raw=True, auto_trust=True)
        if effort:
            inject(name, f"/effort {effort}", raw=True, auto_trust=True)
        os.makedirs(STATE_DIR, exist_ok=True)
        open(LEAD_FILE, "w").write(name)
        print(f"  ✓ registered as lead — watch escalations now go to @{name}")
        if not watch_running():
            subprocess.run(["python3", os.path.join(LIBEXEC, "fleet", "watch.py"),
                            "watch", "on"], check=False)
        print("  " + inject(name, goal_msg, auto_trust=True))
        print(f"✓ orchestrator running. Peek: tess report {name} · tess status")
        print(f"  take back command anytime: tess orchestrate off")
    except AgentError as e:
        die(e.msg, e.code)


if __name__ == "__main__":
    main()
