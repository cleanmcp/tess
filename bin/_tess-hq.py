#!/usr/bin/env python3
# _tess-hq.py — the lead's window into the fleet. Subcommands:
#   report <agent> [--n N] [--json]   full last assistant message(s), plain text
#   digest [--json]                   merged summary of every alive agent
# (inbox/status/wait live in their own helpers; this is read-only reporting.)
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _tess_agents import hcom, list_agents

WORKTREE_ROOT = (os.environ.get("TESS_WORKTREE_ROOT") or os.path.expanduser("~/worktrees")).rstrip("/")


def die(msg, code=1):
    print(f"tess: {msg}", file=sys.stderr)
    sys.exit(code)


def exchanges(agent, n=1):
    r = hcom("transcript", agent, "--json", "--full", "--last", str(n))
    try:
        return json.loads(r.stdout) or []
    except ValueError:
        return []


def nice_dir(d):
    d = d or ""
    if d.startswith(WORKTREE_ROOT + "/"):
        return d[len(WORKTREE_ROOT) + 1:]
    return d.replace(os.path.expanduser("~"), "~")


def age(secs):
    if secs is None:
        return "?"
    secs = int(secs)
    for unit, div in (("s", 1), ("m", 60), ("h", 3600)):
        if secs < div * 60 or unit == "h":
            return f"{secs // div}{unit}"


STATUS_ICON = {"active": "▶", "listening": "◉", "blocked": "■", "inactive": "○"}


def cmd_report(args):
    as_json = "--json" in args
    n = 1
    if "--n" in args:
        i = args.index("--n")
        try:
            n = int(args[i + 1])
            del args[i:i + 2]
        except (IndexError, ValueError):
            die("--n needs a number")
    pos = [a for a in args if not a.startswith("-")]
    if len(pos) != 1:
        die("usage: tess report <agent> [--n N] [--json]")
    agent = pos[0]
    exs = exchanges(agent, n)
    if not exs:
        die(f"no transcript for '{agent}' (see: tess agents)", 2)
    if as_json:
        print(json.dumps(exs, indent=2))
        return
    for ex in exs:
        if len(exs) > 1:
            u = " ".join((ex.get("user") or "").split())
            print(f"── #{ex.get('position')} ── task: {u[:100]}")
        print((ex.get("action") or "(no reply yet)").rstrip())
        if len(exs) > 1:
            print()


def cmd_digest(args):
    as_json = "--json" in args
    agents = list_agents()
    me = os.environ.get("HCOM_SELF")  # optional: skip yourself in a lead loop
    rows = []
    for a in agents:
        if me and a["name"] == me:
            continue
        exs = exchanges(a["name"], 1)
        last = (exs[-1].get("action") or "").strip() if exs else ""
        task = " ".join((exs[-1].get("user") or "").split())[:120] if exs else ""
        rows.append({
            "name": a["name"], "tool": a.get("tool"), "status": a.get("status"),
            "status_detail": a.get("status_detail") or a.get("description") or "",
            "age_s": a.get("status_age_seconds"),
            "dir": nice_dir(a.get("directory")),
            "unread": a.get("unread_count", 0),
            "task": task, "last": last,
        })
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print("no agents running. (spawn: tess claude <feat> \"<task>\")")
        return
    for r in rows:
        icon = STATUS_ICON.get(r["status"], "◦")
        print(f"{icon} {r['name']}  [{r['tool']}]  {r['status']} {age(r['age_s'])}"
              f"  ·  {r['dir']}" + (f"  ·  {r['unread']} unread" if r["unread"] else ""))
        if r["task"]:
            print(f"   task: {r['task']}")
        snippet = r["last"].replace("\n", "\n   ")
        if len(snippet) > 700:
            snippet = snippet[:700] + f" […see: tess report {r['name']}]"
        print(f"   {snippet if snippet else '(no output yet)'}")
        print()


def main():
    args = sys.argv[1:]
    if not args:
        die("usage: _tess-hq.py report|digest …")
    sub = args.pop(0)
    if sub == "report":
        cmd_report(args)
    elif sub == "digest":
        cmd_digest(args)
    else:
        die(f"unknown subcommand '{sub}'")


if __name__ == "__main__":
    main()
