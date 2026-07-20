#!/usr/bin/env python3
# hq.py — the lead's window into the fleet. Subcommands:
#   report <agent> [--n N] [--json]   full last assistant message(s), plain text
#   digest [--json]                   merged summary of every alive agent
#   status [--json]                   fleet table — blocked first, with ages
#   diff <agent|feature> [--full]     what an agent/feature actually changed
#   approve <agent> [--option N]      answer a BLOCKED agent's approval dialog
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_agents import (agents_under, brand, hcom, list_agents, press,
                          screen_text, scrub, status_of, term_state)

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
        print(scrub(ex.get("action")) or "(no reply yet)")
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
        last = scrub(exs[-1].get("action")) if exs else ""
        task = " ".join(scrub(exs[-1].get("user")).split())[:120] if exs else ""
        rows.append({
            "name": a["name"], "tool": a.get("tool"), "status": a.get("status"),
            "status_detail": brand(a.get("status_detail") or a.get("description")),
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


RANK = {"blocked": 0, "active": 1, "listening": 2}


def cmd_status(args):
    as_json = "--json" in args
    rows = []
    for a in list_agents():
        rows.append({
            "name": a["name"], "tool": a.get("tool"), "status": a.get("status"),
            "detail": " ".join(brand(a.get("status_detail") or a.get("description")).split()),
            "age_s": a.get("status_age_seconds"), "dir": nice_dir(a.get("directory")),
            "unread": a.get("unread_count", 0), "tag": a.get("tag"),
        })
    rows.sort(key=lambda r: (RANK.get(r["status"], 3), r["name"]))
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print("no agents running. (spawn: tess claude <feat> \"<task>\" · fan out: tess team)")
        return
    blocked = [r for r in rows if r["status"] == "blocked"]
    for r in rows:
        icon = STATUS_ICON.get(r["status"], "◦")
        line = (f"{icon} {r['name']:<18} {r['status']:<10} {age(r['age_s']):>4}"
                f"  {r['dir']:<30.30}  {r['detail'][:44]}")
        if r["unread"]:
            line += f"  [{r['unread']} unread]"
        print(line)
    print()
    if blocked:
        print(f"■ {len(blocked)} BLOCKED on approval — tess approve "
              f"{' / '.join(r['name'] for r in blocked)}")
    print("zoom: tess report <agent> · changes: tess diff <agent|feat> · mail: tess inbox")


def _repo_diff(rdir, full):
    def git(*a):
        return subprocess.run(["git", "-C", rdir, *a], capture_output=True, text=True).stdout
    porc = git("status", "--porcelain")
    stat = git("diff", "--stat", "HEAD")
    out = []
    if porc.strip():
        out.append(porc.rstrip())
    if stat.strip():
        out.append(stat.rstrip())
    if full:
        d = git("diff", "HEAD")
        if d.strip():
            out.append(d.rstrip())
    return "\n".join(out)


def cmd_diff(args):
    full = "--full" in args
    pos = [a for a in args if not a.startswith("-")]
    if len(pos) != 1:
        die("usage: tess diff <agent|feature> [--full]")
    tgt = pos[0]
    fdir = os.path.join(WORKTREE_ROOT, tgt)
    dirs = []
    if os.path.isdir(fdir):
        for sub in sorted(os.listdir(fdir)):
            if os.path.exists(os.path.join(fdir, sub, ".git")):
                dirs.append((f"{tgt}/{sub}", os.path.join(fdir, sub)))
    else:
        info = next((a for a in list_agents() if a["name"] == tgt), None)
        if not info:
            die(f"'{tgt}' is neither a feature nor a running agent", 2)
        d = info.get("directory") or ""
        if os.path.exists(os.path.join(d, ".git")):
            dirs.append((nice_dir(d), d))
        else:  # agent sits at a feature root — diff each worktree inside
            for sub in sorted(os.listdir(d) if os.path.isdir(d) else []):
                if os.path.exists(os.path.join(d, sub, ".git")):
                    dirs.append((f"{nice_dir(d)}/{sub}", os.path.join(d, sub)))
    if not dirs:
        die(f"no git worktrees found for '{tgt}'", 2)
    any_out = False
    for label, d in dirs:
        body = _repo_diff(d, full)
        if body:
            any_out = True
            print(f"== {label} ==")
            print(body)
            print()
    if not any_out:
        print("clean — no uncommitted changes." )


def cmd_approve(args):
    option = None
    if "--option" in args:
        try:
            option = args[args.index("--option") + 1]
        except IndexError:
            die("--option needs a number")
    pos = [a for a in args if not a.startswith("-") and a != option]
    if len(pos) != 1:
        die("usage: tess approve <agent> [--option N]")
    agent = pos[0]
    st = status_of(agent)
    if st is None:
        die(f"no agent named '{agent}' (see: tess status)")
    if st != "blocked":
        die(f"'{agent}' is not blocked (status: {st}) — nothing to approve", 2)
    scr = [l for l in (term_state(agent) or {}).get("lines", []) if l.strip()]
    print("dialog:")
    for l in scr[-10:]:
        print(f"  {l.rstrip()}")
    if option:
        press(agent, option)
    press(agent, "enter")
    for _ in range(10):
        time.sleep(1.5)
        st = status_of(agent)
        if st != "blocked":
            print(f"✓ {agent} unblocked (now {st})")
            return
    die(f"'{agent}' is still blocked — check the pane: tess agents", 3)


def main():
    args = sys.argv[1:]
    if not args:
        die("usage: hq.py report|digest|status|diff|approve …")
    sub = args.pop(0)
    if sub == "report":
        cmd_report(args)
    elif sub == "digest":
        cmd_digest(args)
    elif sub == "status":
        cmd_status(args)
    elif sub == "diff":
        cmd_diff(args)
    elif sub == "approve":
        cmd_approve(args)
    else:
        die(f"unknown subcommand '{sub}'")


if __name__ == "__main__":
    main()
