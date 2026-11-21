#!/usr/bin/env python3
"""List the persistent shells on THIS machine, with what is running in each.

`tess <node> ls` pipes this file to the node's python3 over ssh, so nothing has
to be installed there for it to work. A session is a dtach socket at
~/.dtach-<name> holding a login shell; it is parented to init, not to sshd,
which is why it outlives the connection that started it.

    (no flag)   table: session / uptime / cwd / running command
    --idle      only the names of sessions running nothing
    --names     every session name
    --json      [{"name", "uptime", "cwd", "running": [...]}]

Stdlib only, python 3.6+, macOS and Linux.
"""
import json
import os
import re
import subprocess
import sys

ps = subprocess.run(["ps", "-axo", "pid=,ppid=,etime=,command="],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    universal_newlines=True).stdout
procs, kids = {}, {}
for ln in ps.splitlines():
    m = re.match(r"\s*(\d+)\s+(\d+)\s+(\S+)\s+(.*)", ln)
    if not m:
        continue
    pid, ppid = int(m.group(1)), int(m.group(2))
    procs[pid] = (ppid, m.group(3), m.group(4))
    kids.setdefault(ppid, []).append(pid)


def cwd(pid):
    try:                                   # Linux
        return os.readlink("/proc/%d/cwd" % pid)
    except OSError:
        pass
    try:                                   # macOS
        out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             universal_newlines=True).stdout
    except OSError:
        return "?"
    for line in out.splitlines():
        if line.startswith("n"):
            return line[1:]
    return "?"


HOME = os.path.expanduser("~")
SHELLS = ("zsh", "bash", "sh", "fish", "dash")


def is_shell(cmd):
    head = os.path.basename(cmd.split(" ", 1)[0]).lstrip("-")
    return head in SHELLS


# dtach -A shows up twice while someone is attached: the master that owns the
# shell, and the attached client (same command line, no children). Keep the
# master — the one with children — once per name.
masters = {}
for pid, (ppid, et, cmd) in procs.items():
    m = re.search(r"dtach -A \S*\.dtach-(\S+)", cmd)
    if not m:
        continue
    name = m.group(1)
    if name not in masters or (kids.get(pid) and not kids.get(masters[name])):
        masters[name] = pid

rows = []
for name, pid in masters.items():
    ppid, et, cmd = procs[pid]
    shell = next(iter(kids.get(pid, [])), None)
    running, stack = [], list(kids.get(pid, []))
    while stack:
        c = stack.pop()
        stack += kids.get(c, [])
        cc = procs[c][2]
        if is_shell(cc) or "<defunct>" in cc:
            continue
        running.append(cc)
    d = cwd(shell) if shell else "?"
    if d == HOME or d.startswith(HOME + "/"):
        d = "~" + d[len(HOME):]
    rows.append((name, et, d, running))

rows.sort(key=lambda r: (not r[3], r[0]))

if "--idle" in sys.argv:
    print("\n".join(n for n, _, _, r in rows if not r))
elif "--names" in sys.argv:
    print("\n".join(n for n, _, _, _ in rows))
elif "--json" in sys.argv:
    print(json.dumps([{"name": n, "uptime": e, "cwd": d, "running": r}
                      for n, e, d, r in rows]))
else:
    tty = sys.stdout.isatty() or "--color" in sys.argv
    B, D, R = ("\033[1m", "\033[2m", "\033[0m") if tty else ("", "", "")
    w = max([len(r[0]) for r in rows] + [7])
    for name, et, d, running in rows:
        head = running[0][:78] if running else D + "— idle —" + R
        print("%s%-*s%s  %12s  %-34s %s" % (B, w, name, R, et, d, head))
        for extra in running[1:4]:
            print("%-*s  %12s  %-34s %s" % (w, "", "", "", extra[:78]))
