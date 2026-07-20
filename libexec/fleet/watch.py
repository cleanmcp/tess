#!/usr/bin/env python3
# watch.py — F2 wait + F6 escalation. No stuck sub-agent goes unnoticed.
#
#   wait <agent|feature|all> [--timeout N] [--interval N]
#       block until the target(s) stop working. Exit: 0 all idle/finished,
#       2 something is BLOCKED on approval, 3 timeout, 4 something died.
#
#   watch [--phone] [--once] [--interval N]      foreground escalation loop
#   watch on [--phone] / off / status            background daemon (nohup)
#
# Escalation (F6): the moment ANY agent needs input — BLOCKED on an approval
# prompt, DIED, or gone IDLE mid-task (stable >20s) — the lead is pinged:
#   → hcom DM to the lead identity (~/.config/tess/state/lead, default
#     bigboss). A human lead reads it in `tess inbox`; an AI orchestrator
#     (tess orchestrate writes its agent name there) gets it delivered
#     straight into its conversation.
#   → optionally the user's phone (--phone + TESS_NOTIFY_CONTACT via iMessage).
import base64
import json
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_agents import agents_under, hcom, list_agents

WORKTREE_ROOT = (os.environ.get("TESS_WORKTREE_ROOT") or os.path.expanduser("~/worktrees")).rstrip("/")
LIBEXEC = os.environ.get("TESS_LIB") or os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
STATE_DIR = os.path.expanduser("~/.config/tess/state")
SNAP = os.path.join(STATE_DIR, "watch-snapshot.json")
PIDF = os.path.join(STATE_DIR, "watch.pid")
LOGF = os.path.join(STATE_DIR, "watch.log")
LEAD_FILE = os.path.join(STATE_DIR, "lead")
NOTIFY = os.environ.get("TESS_NOTIFY_CONTACT", "")
IDLE_STABLE = int(os.environ.get("TESS_IDLE_STABLE_SECS", "20"))


def die(msg, code=1):
    print(f"tess: {msg}", file=sys.stderr)
    sys.exit(code)


def lead_name():
    try:
        return open(LEAD_FILE).read().strip() or "bigboss"
    except OSError:
        return "bigboss"


def log(msg):
    line = f"{time.strftime('%F %T')} {msg}"
    print(line, flush=True)
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LOGF, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def escalate(name, kind, detail, phone):
    lead = lead_name()
    hints = {"BLOCKED": f"approve it: tess approve {name}",
             "IDLE": f"next step: tess report {name} · tess tell {name} -- <instruction>",
             "DIED": f"restart: tess resume — pick {name}"}
    msg = (f"⚠ ESCALATION: {name} is {kind} — {detail}\n{hints[kind]}")
    b64 = base64.b64encode(msg.encode()).decode()
    hcom("send", f"@{lead}", "--from", "tess-watch", "--intent", "request", "--base64", b64)
    if phone and NOTIFY:
        subprocess.run(["bash", os.path.join(LIBEXEC, "life", "send.sh"), NOTIFY, "--",
                        f"tess: {name} {kind} — {detail[:120]}"],
                       capture_output=True, text=True)
    log(f"escalated: {name} {kind} → @{lead}" + (" + phone" if phone and NOTIFY else ""))


def load_snap():
    try:
        return json.load(open(SNAP))
    except (OSError, ValueError):
        return {}


def save_snap(s):
    os.makedirs(STATE_DIR, exist_ok=True)
    json.dump(s, open(SNAP, "w"))


def scan(prev, phone):
    """One escalation pass. Returns the new snapshot."""
    now = time.time()
    lead = lead_name()
    snap = {}
    alive = {a["name"]: a for a in list_agents()}
    for name, a in alive.items():
        if name == lead:
            snap[name] = {"status": a.get("status"), "since": now, "idle_fired": True}
            continue  # never escalate the lead to itself
        st = a.get("status") or "unknown"
        old = prev.get(name, {})
        entry = {"status": st,
                 "since": old.get("since", now) if old.get("status") == st else now,
                 "idle_fired": old.get("idle_fired", False)}
        detail = a.get("status_detail") or a.get("description") or ""
        if st == "blocked" and old.get("status") != "blocked":
            escalate(name, "BLOCKED", detail or "waiting on an approval prompt", phone)
        elif st == "listening":
            if old.get("status") == st and not entry["idle_fired"] \
                    and now - entry["since"] >= IDLE_STABLE:
                escalate(name, "IDLE", "finished/waiting with no new instruction", phone)
                entry["idle_fired"] = True
        else:
            entry["idle_fired"] = False
        snap[name] = entry
    for name, old in prev.items():
        if name not in alive and old.get("status") not in (None, "inactive"):
            escalate(name, "DIED", f"was {old.get('status')}, no longer running", phone)
    return snap


def cmd_watch(args):
    phone = "--phone" in args
    once = "--once" in args
    interval = 5
    if "--interval" in args:
        try:
            interval = int(args[args.index("--interval") + 1])
        except (IndexError, ValueError):
            die("--interval needs a number")

    sub = next((a for a in args if a in ("on", "off", "status")), None)
    if sub == "off":
        try:
            pid = int(open(PIDF).read().strip())
            os.kill(pid, signal.SIGTERM)
            os.remove(PIDF)
            print(f"✓ watcher stopped (pid {pid})")
        except (OSError, ValueError):
            print("no watcher running.")
        return
    if sub == "status":
        try:
            pid = int(open(PIDF).read().strip())
            os.kill(pid, 0)
            print(f"watcher running (pid {pid}), log: {LOGF}")
        except (OSError, ValueError):
            print("watcher not running. start: tess watch on [--phone]")
        return
    if sub == "on":
        try:
            pid = int(open(PIDF).read().strip())
            os.kill(pid, 0)
            die(f"already running (pid {pid}) — tess watch off first")
        except (OSError, ValueError):
            pass
        cmd = [sys.executable, os.path.realpath(__file__), "watch", "--interval", str(interval)]
        if phone:
            cmd.append("--phone")
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LOGF, "a") as lf:
            p = subprocess.Popen(cmd, stdout=lf, stderr=lf,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
        open(PIDF, "w").write(str(p.pid))
        print(f"✓ watcher on (pid {p.pid}, every {interval}s"
              + (", phone pings" if phone else "") + f") — log: {LOGF}")
        return

    # foreground loop (also the daemon's body) / --once single pass
    prev = load_snap()
    while True:
        prev = scan(prev, phone)
        save_snap(prev)
        if once:
            return
        time.sleep(interval)


def cmd_wait(args):
    timeout, interval = 7200, 3
    if "--timeout" in args:
        try:
            timeout = int(args[args.index("--timeout") + 1])
        except (IndexError, ValueError):
            die("--timeout needs a number")
    if "--interval" in args:
        try:
            interval = int(args[args.index("--interval") + 1])
        except (IndexError, ValueError):
            die("--interval needs a number")
    pos = [a for a in args if not a.startswith("-") and not a.isdigit()]
    if len(pos) != 1:
        die("usage: tess wait <agent|feature|all> [--timeout N]")
    spec = pos[0]

    def resolve():
        if spec == "all":
            return {a["name"]: a for a in list_agents()}
        fdir = os.path.join(WORKTREE_ROOT, spec)
        if os.path.isdir(fdir):
            return {a["name"]: a for a in agents_under(fdir)}
        return {a["name"]: a for a in list_agents() if a["name"] == spec}

    names = set(resolve())
    if not names:
        die(f"nothing to wait for: no agent/feature '{spec}'", 4)
    print(f"waiting on: {', '.join(sorted(names))}")
    last = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        alive = {a["name"]: a for a in list_agents()}
        states = {}
        for n in names:
            states[n] = alive[n]["status"] if n in alive else "inactive"
            if last.get(n) != states[n]:
                print(f"  {n}: {states[n]}", flush=True)
                last[n] = states[n]
        if all(s in ("listening", "blocked", "inactive") for s in states.values()):
            blocked = [n for n, s in states.items() if s == "blocked"]
            dead = [n for n, s in states.items() if s == "inactive"]
            if blocked:
                print(f"■ BLOCKED on approval: {', '.join(blocked)} — tess approve <agent>")
                sys.exit(2)
            if dead:
                print(f"○ died/stopped: {', '.join(dead)}")
                sys.exit(4)
            print("✓ all idle/finished — read them: tess digest")
            sys.exit(0)
        time.sleep(interval)
    print(f"timed out after {timeout}s (still working)")
    sys.exit(3)


def main():
    args = sys.argv[1:]
    if not args:
        die("usage: watch.py wait|watch …")
    sub = args.pop(0)
    if sub == "wait":
        cmd_wait(args)
    elif sub == "watch":
        cmd_watch(args)
    else:
        die(f"unknown subcommand '{sub}'")


if __name__ == "__main__":
    main()
