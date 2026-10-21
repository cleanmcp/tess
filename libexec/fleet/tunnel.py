#!/usr/bin/env python3
"""tess tunnel — reach a peer's localhost from this machine.

    tess tunnel mini 3000              peer's :3000 shows up as http://localhost:3000
    tess tunnel mini 3000 5173 8080    several at once
    tess tunnel mini 3900:3000         different local port (when 3000 is taken here)
    tess tunnel mini --login           the ports agent sign-ins call back on
    tess tunnel mini --bg 3000         leave it running in the background
    tess tunnel --list                 what this machine is forwarding
    tess tunnel --stop                 close the backgrounded ones

Two problems, one answer.

**Seeing what an agent built.** A dev server on a peer usually binds 127.0.0.1,
so nothing outside that machine can reach it — and loosening the bind would put
it on the network. Forwarding the port instead keeps it private and makes it
show up on this machine as plain localhost, which is also the origin that cookies,
CORS rules and OAuth redirect allow-lists already expect.

**Signing in on a machine with no screen.** A CLI sign-in opens a browser and
waits for a redirect to 127.0.0.1:<port> — on the machine that started it. Run it
over ssh and the browser is here while the listener is there, so the redirect
lands on the wrong computer and the sign-in hangs. Forward that port first and
this machine's localhost *is* the peer's listener, so the redirect arrives where
it is being waited for. --login forwards the ports the common agent CLIs use.

Peers come from TESS_PEERS (see `tess help handoff`); the forward itself is
plain `ssh -L`, so nothing listens on any external interface.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_common import C  # noqa: E402

HOME = os.path.expanduser("~")
STATE = os.path.join(os.environ.get("TESS_STATE") or
                     os.path.join(HOME, ".local/share/tess"), "tunnels")
# Ports the agent CLIs wait on for a sign-in redirect. Claude Code and Codex each
# pin one; Gemini picks a free port and prints it, so it needs <local>:<remote>.
LOGIN_PORTS = [54545, 1455]


def die(msg, code=1):
    print(f"{C.red}✗{C.r} {msg}", file=sys.stderr)
    sys.exit(code)


def peers():
    """{name: ssh target} from TESS_PEERS — env first, then the config file."""
    raw = os.environ.get("TESS_PEERS")
    if raw is None:
        try:
            with open(os.path.join(HOME, ".config", "tess", "config")) as fh:
                for line in fh:
                    m = re.match(r'\s*TESS_PEERS\s*=\s*"?([^"#]*)"?', line)
                    if m:
                        raw = m.group(1)
        except OSError:
            pass
    out = {}
    for entry in (raw or "").split():
        if "=" in entry:
            name, target = entry.split("=", 1)
            if name and target:
                out[name.lower()] = target
    return out


def parse_port(spec):
    """"3000" -> (3000, 3000) · "3900:3000" -> (3900, 3000)"""
    parts = spec.split(":")
    if len(parts) > 2 or not all(p.isdigit() for p in parts):
        die(f"'{spec}' isn't a port or <local>:<remote> pair")
    nums = [int(p) for p in parts]
    for n in nums:
        if not 1 <= n <= 65535:
            die(f"port {n} is out of range")
    return (nums[0], nums[-1])


def in_use(port):
    """True if something here already listens on that port."""
    lsof = shutil.which("lsof")
    if not lsof:
        return False
    p = subprocess.run([lsof, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                       capture_output=True, text=True)
    return p.returncode == 0 and bool(p.stdout.strip())


def read_state():
    try:
        with open(STATE) as fh:
            return [l.strip().split("\t") for l in fh if l.strip()]
    except OSError:
        return []


def write_state(rows):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as fh:
        for r in rows:
            fh.write("\t".join(str(x) for x in r) + "\n")


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def do_list():
    rows = [r for r in read_state() if len(r) == 4 and alive(r[0])]
    write_state(rows)                      # prune dead ones as we go
    print(f"\n{C.bold}tunnels{C.r}\n")
    if not rows:
        print(f"  {C.grey}none in the background{C.r}")
        print(f"  {C.grey}(a foreground `tess tunnel` isn't listed — it's the one you "
              f"can see){C.r}\n")
        return
    for pid, peer, local, remote in rows:
        print(f"  {C.green}localhost:{local}{C.r}  {C.grey}→ {peer}:{remote} · pid {pid}{C.r}")
    print(f"\n  {C.grey}close them:  tess tunnel --stop{C.r}\n")


def do_stop():
    rows = read_state()
    stopped = 0
    for pid, peer, local, remote in [r for r in rows if len(r) == 4]:
        if alive(pid):
            try:
                os.kill(int(pid), 15)
                stopped += 1
                print(f"  closed {C.bold}localhost:{local}{C.r} → {peer}:{remote}")
            except OSError as e:
                print(f"  {C.yellow}couldn't close pid {pid}: {e}{C.r}")
    write_state([])
    print(f"{C.green}✓{C.r} {stopped} closed" if stopped
          else f"{C.grey}nothing was running{C.r}")


def main():
    ap = argparse.ArgumentParser(
        prog="tess tunnel", add_help=True,
        description="Reach a peer's localhost from this machine: forward one or more "
                    "ports over ssh, so the peer's 127.0.0.1 shows up as yours.",
        epilog='peers live in ~/.config/tess/config:  TESS_PEERS="mini=<ssh target>"')
    ap.add_argument("peer", nargs="?", help="peer name")
    ap.add_argument("ports", nargs="*", help="<port> or <local>:<remote>")
    ap.add_argument("--login", action="store_true",
                    help="forward the ports agent CLI sign-ins redirect to")
    ap.add_argument("--bg", action="store_true", help="run in the background")
    ap.add_argument("--list", action="store_true", help="show background tunnels")
    ap.add_argument("--stop", action="store_true", help="close background tunnels")
    # argparse can't interleave a flag with a greedy positional list, so
    # `tunnel mini --bg 3000` would reject the port. Take the leftovers as ports.
    args, rest = ap.parse_known_args()
    bad = [a for a in rest if a.startswith("-")]
    if bad:
        ap.error(f"unrecognized arguments: {' '.join(bad)}")
    args.ports = list(args.ports) + rest

    if args.list:
        return do_list()
    if args.stop:
        return do_stop()
    if not args.peer:
        ap.print_help()
        return

    ps = peers()
    if not ps:
        die('no peers configured. Add one to ~/.config/tess/config:\n\n'
            '    TESS_PEERS="mini=<ssh target>"\n')
    name = args.peer.lower()
    if name not in ps:
        die(f"unknown peer '{name}' — configured: {', '.join(ps)}")
    if not shutil.which("ssh"):
        die("ssh isn't on this machine")

    pairs = [parse_port(p) for p in args.ports]
    if args.login:
        pairs += [(p, p) for p in LOGIN_PORTS if (p, p) not in pairs]
    if not pairs:
        die("name at least one port, or pass --login\n"
            f"  e.g.  tess tunnel {name} 3000")

    # A local port already in use would make ssh bind-fail per port; say so first.
    for local, remote in pairs:
        if in_use(local):
            die(f"localhost:{local} is already in use here.\n"
                f"  Pick another local port:  tess tunnel {name} <free>:{remote}")

    target = ps[name]
    cmd = ["ssh", "-N", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30"]
    for local, remote in pairs:
        cmd += ["-L", f"{local}:localhost:{remote}"]
    cmd.append(target)

    shown = "  ".join(f"localhost:{l} → {name}:{r}" for l, r in pairs)
    if args.bg:
        cmd.insert(1, "-f")                      # ssh backgrounds itself once forwarded
        subprocess.run(cmd, check=False)
        # -f forks, so find the child it left behind rather than trusting our pid
        pgrep = shutil.which("pgrep")
        pid = ""
        if pgrep:
            pat = f"ssh -f -N.*{pairs[0][0]}:localhost:{pairs[0][1]}"
            got = subprocess.run([pgrep, "-n", "-f", pat], capture_output=True, text=True)
            pid = got.stdout.strip().splitlines()[0] if got.stdout.strip() else ""
        if pid:
            write_state(read_state() + [[pid, name, l, r] for l, r in pairs])
        print(f"{C.green}✓{C.r} {shown}")
        print(f"  {C.grey}close with:  tess tunnel --stop{C.r}")
        if args.login:
            print(f"  {C.grey}now run the sign-in on {name} — its redirect will reach "
                  f"this machine's browser{C.r}")
        return

    print(f"{C.green}✓{C.r} {shown}")
    if args.login:
        print(f"  {C.grey}leave this open, then run the sign-in on {name}{C.r}")
    print(f"  {C.grey}Ctrl-C to close{C.r}")
    try:
        os.execvp(cmd[0], cmd)               # hand the terminal straight to ssh
    except OSError as e:
        die(f"couldn't start ssh: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
