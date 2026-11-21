#!/usr/bin/env python3
"""tess node — your other machines, as one surface.

    tess node                         every node: reachable? tess? what's running there
    tess node add <name> <user@host>  set a machine up end to end (key, ssh alias, tess, tools)
    tess node add                     …or just answer two questions
    tess node setup <name>            re-run the setup on a node (safe to repeat)
    tess node rm <name>               forget a node (nothing is deleted on it)
    tess node me                      how to add THIS machine from another one

Once a node exists its name is a command:

    tess mini                         a persistent shell there (survives closing the laptop)
    tess mini api                     another one, named "api" — a name per tab
    tess mini ls                      every shell there + what is running in it
    tess mini kill api · clean · killall
    tess mini run <cmd…>              one command, with that machine's real PATH
    tess mini handoff [--pick]        move this folder's live session there
    tess mini back                    take it back
    tess mini tunnel 3000             its localhost:3000, here
    tess mini pull [<path>…]          copy files down (no path = what the agents made)
    tess mini new <feature>           cut a worktree there
    tess mini ssh                     a plain ssh, no persistence

A node is one entry in TESS_PEERS (~/.config/tess/config) — the same setting
`tess handoff`, `tess tunnel` and `tess new --on` read — pointing at a Host
alias in ~/.ssh/config. `tess node add` writes both, installs your key, and
installs tess + dtach on the other side. Every step is idempotent and reported;
nothing is half-registered if the machine can't be reached.
"""
import concurrent.futures
import getpass
import json
import os
import re
import shutil
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from tess_common import C  # noqa: E402
from tess_peers import CONFIG, login_shell, peers, q, remote_tess  # noqa: E402

HOME = os.path.expanduser("~")
SSH_DIR = os.path.join(HOME, ".ssh")
SSH_CONFIG = os.path.join(SSH_DIR, "config")
TESS_HOME = os.path.realpath(os.path.join(HERE, "..", ".."))
TESS_BIN = os.path.join(TESS_HOME, "bin", "tess")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
# words `tess <node> <word>` treats as an action rather than a session name
VERBS = {"ls", "st", "status", "kill", "clean", "killall", "run", "ssh", "handoff",
         "send", "back", "tunnel", "pull", "sync", "new", "setup", "check", "rm"}
OK, NO, DOT = "✓", "✗", "·"


def die(msg, code=1):
    print(f"{C.red}tess node:{C.r} {msg}", file=sys.stderr)
    sys.exit(code)


def step(mark, text, detail=""):
    color = {OK: C.green, NO: C.red}.get(mark, C.grey)
    tail = f"  {C.grey}{detail}{C.r}" if detail else ""
    print(f"  {color}{mark}{C.r} {text}{tail}", flush=True)


def interactive():
    return sys.stdin.isatty() and sys.stdout.isatty()


# ---------------------------------------------------------------- config

def reserved():
    words = set(os.environ.get("TESS_RESERVED", "").split())
    return words | {"node", "nodes", "add", "me", "on"} | VERBS


def config_peers():
    """{name: target} as written in the config file (not the environment) —
    the thing `add` and `rm` edit."""
    try:
        text = open(CONFIG).read()
    except OSError:
        return {}
    raw = ""
    for m in re.finditer(r'^[ \t]*TESS_PEERS[ \t]*=[ \t]*"?([^"#\n]*)"?', text, re.M):
        raw = m.group(1)
    out = {}
    for entry in raw.split():
        if "=" in entry:
            n, t = entry.split("=", 1)
            if n and t:
                out[n.lower()] = t
    return out


def write_config_peers(ps):
    """Rewrite the TESS_PEERS line in place (the last one wins, as in bash),
    or append one. Everything else in the file is left byte-identical."""
    line = 'TESS_PEERS="' + " ".join(f"{n}={t}" for n, t in ps.items()) + '"'
    try:
        text = open(CONFIG).read()
    except OSError:
        text = ""
    hits = list(re.finditer(r'^[ \t]*TESS_PEERS[ \t]*=.*$', text, re.M))
    if hits:
        last = hits[-1]
        text = text[:last.start()] + line + text[last.end():]
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += ("\n# nodes — other machines you work on (managed by `tess node add`/`rm`)\n"
                 + line + "\n")
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    tmp = CONFIG + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(text)
    os.replace(tmp, CONFIG)


# ---------------------------------------------------------------- ssh config

def _begin(name):
    return f"# >>> tess node: {name}"


def _end(name):
    return f"# <<< tess node: {name}"


def ssh_config_text():
    try:
        return open(SSH_CONFIG).read()
    except OSError:
        return ""


def managed_block(name):
    m = re.search(re.escape(_begin(name)) + r"\n.*?" + re.escape(_end(name)) + r"\n?",
                  ssh_config_text(), re.S)
    return m.group(0) if m else None


def alias_defined(name):
    """Is there a `Host <name>` line in ~/.ssh/config (ours or the user's)?"""
    for line in ssh_config_text().splitlines():
        m = re.match(r"\s*Host\s+(.*)", line, re.I)
        if m and name in m.group(1).split():
            return True
    return False


def write_ssh_block(name, user, host, port):
    os.makedirs(os.path.join(SSH_DIR, "cm"), mode=0o700, exist_ok=True)
    lines = [_begin(name), f"Host {name}", f"  HostName {host}"]
    if user:
        lines.append(f"  User {user}")
    if port:
        lines.append(f"  Port {port}")
    lines += ["  ServerAliveInterval 30", "  ServerAliveCountMax 6", "  TCPKeepAlive yes",
              "  ConnectTimeout 15",
              "  # one connection reused for tess's many one-shot ssh calls",
              "  ControlMaster auto", "  ControlPath ~/.ssh/cm/%C", "  ControlPersist 10m",
              _end(name)]
    block = "\n".join(lines) + "\n"
    text = ssh_config_text()
    old = managed_block(name)
    if old:
        text = text.replace(old, block)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += ("\n" if text else "") + block
    tmp = SSH_CONFIG + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.replace(tmp, SSH_CONFIG)


def remove_ssh_block(name):
    old = managed_block(name)
    if not old:
        return False
    text = ssh_config_text()
    # take back the blank line `add` put in front of the block, and nothing else
    text = text.replace("\n\n" + old, "\n", 1) if "\n\n" + old in text else text.replace(old, "", 1)
    tmp = SSH_CONFIG + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.replace(tmp, SSH_CONFIG)
    return True


def resolved(target):
    """What ssh will actually connect to for this target: (user, host, port)."""
    p = subprocess.run(["ssh", "-G", target], capture_output=True, text=True)
    got = {}
    for line in p.stdout.splitlines():
        k, _, v = line.partition(" ")
        if k in ("user", "hostname", "port"):
            got[k] = v
    return got.get("user", ""), got.get("hostname", target), got.get("port", "22")


def parse_address(addr):
    """user@host[:port] -> (user, host, port). ssh://user@host:port also works."""
    a = addr.strip()
    a = re.sub(r"^ssh://", "", a)
    user, host, port = "", a, ""
    if "@" in a:
        user, host = a.rsplit("@", 1)
    m = re.match(r"^(.*):(\d+)$", host)
    if m and host.count(":") == 1:
        host, port = m.group(1), m.group(2)
    if not host or re.search(r"[\s'\"`$;&|<>\\]", host) or re.search(r"[\s'\"`$;&|<>\\@]", user):
        die(f"'{addr}' doesn't look like user@host")
    return user, host, port


# ---------------------------------------------------------------- reaching a node

def run_ssh(target, script, timeout=None, stdin_text=None, connect=10):
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={connect}", target, script]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              input=stdin_text)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "timed out")


def why(p):
    """One human line for a failed ssh."""
    err = (p.stderr or p.stdout or "").strip().splitlines()
    err = [e for e in err if not e.startswith("Warning: Permanently added")]
    last = err[-1] if err else "no output"
    if "timed out" in last.lower():
        return "timed out — is it awake, and on the same network / VPN / tailnet?"
    if "Permission denied" in last:
        return "it answered, but your ssh key isn't accepted there"
    if "Could not resolve" in last:
        return "that hostname doesn't resolve"
    if "refused" in last.lower():
        return "connection refused — is Remote Login (sshd) turned on there?"
    return last[:160]


def ensure_key():
    for kind in ("id_ed25519", "id_ecdsa", "id_rsa"):
        if os.path.exists(os.path.join(SSH_DIR, kind + ".pub")):
            return os.path.join(SSH_DIR, kind + ".pub"), False
    os.makedirs(SSH_DIR, mode=0o700, exist_ok=True)
    path = os.path.join(SSH_DIR, "id_ed25519")
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", path,
                    "-C", f"{getpass.getuser()}@{socket.gethostname()}"], check=True)
    return path + ".pub", True


def install_key(target, pub):
    """Put our public key on the node. Asks for its password once, on the
    terminal; or reads it from $SSHPASS when sshpass is installed (scripts)."""
    base = ["ssh-copy-id", "-i", pub, "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ControlMaster=no", "-o", "ControlPath=none"]
    if os.environ.get("SSHPASS") and shutil.which("sshpass"):
        p = subprocess.run(["sshpass", "-e"] + base +
                           ["-o", "PreferredAuthentications=password,keyboard-interactive",
                            "-o", "PubkeyAuthentication=no", "-o", "NumberOfPasswordPrompts=1",
                            target], capture_output=True, text=True)
        return p.returncode == 0
    if not interactive():
        return False
    print(f"    {C.grey}its password, once — after this it's key-only:{C.r}", flush=True)
    return subprocess.run(base + [target]).returncode == 0


def reach(target, label, allow_key_install=True):
    """Make key-based ssh work. Returns (ok, detail)."""
    opts = ["-o", "StrictHostKeyChecking=accept-new"]
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12"] + opts +
                       [target, "true"], capture_output=True, text=True)
    if p.returncode == 0:
        return True, "key accepted"
    if "Permission denied" not in (p.stderr or "") or not allow_key_install:
        return False, why(p)
    pub, made = ensure_key()
    if made:
        step(OK, "made an ssh key", pub.replace(HOME, "~"))
    if not install_key(target, pub):
        hint = ("wrong password, or password login is off there" if interactive() or
                os.environ.get("SSHPASS") else
                f"needs its password once — run this in a terminal, or:  ssh-copy-id {target}")
        return False, hint
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", target, "true"],
                       capture_output=True, text=True)
    return (True, "key installed") if p.returncode == 0 else (False, why(p))


# ---------------------------------------------------------------- remote setup

FACTS = r'''
printf 'os=%s\n' "$(uname -s)"
printf 'home=%s\n' "$HOME"
for t in git rsync python3 dtach brew apt-get dnf pacman; do
  printf 'has_%s=%s\n' "$t" "$(command -v "$t" 2>/dev/null)"
done
'''


def facts(target):
    p = run_ssh(target, login_shell(FACTS), timeout=60)
    out = {}
    for line in p.stdout.splitlines():
        k, eq, v = line.partition("=")
        if eq and re.match(r"^[a-z_0-9-]+$", k):
            out[k] = v.strip()
    return out


def install_dtach(target, f):
    if f.get("has_dtach"):
        return True, "already there"
    if f.get("has_brew"):
        cmd = "HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_ENV_HINTS=1 brew install dtach"
    elif f.get("has_apt-get"):
        cmd = "sudo -n apt-get install -y dtach"
    elif f.get("has_dnf"):
        cmd = "sudo -n dnf install -y dtach"
    elif f.get("has_pacman"):
        cmd = "sudo -n pacman -S --noconfirm dtach"
    else:
        return False, "no package manager found — install dtach there by hand"
    p = run_ssh(target, login_shell(cmd + " >/dev/null 2>&1; command -v dtach"), timeout=600)
    if p.stdout.strip():
        return True, "installed"
    return False, f"couldn't install it — on the node run:  {cmd.replace('sudo -n', 'sudo')}"


def origin_url():
    p = subprocess.run(["git", "-C", TESS_HOME, "remote", "get-url", "origin"],
                       capture_output=True, text=True)
    return p.stdout.strip()


def local_version():
    p = subprocess.run([TESS_BIN, "--version"], capture_output=True, text=True)
    return p.stdout.strip()


def install_tess(target, f):
    """Get tess onto the node: clone it there if it can, else push ours over
    ssh (works for a private repo and with no internet on the node)."""
    found = remote_tess(target)
    if found:
        v = run_ssh(target, f"{q(found)} --version", timeout=30).stdout.strip()
        return True, v or "installed"
    if not f.get("has_git"):
        return False, "git is missing there — install git, then:  tess node setup"
    has_repo = run_ssh(target, 'test -d "$HOME/tess/.git" && echo y', timeout=30).stdout.strip()
    how = "already cloned"
    if not has_repo:
        exists = run_ssh(target, 'test -e "$HOME/tess" && echo y', timeout=30).stdout.strip()
        if exists:
            return False, "~/tess exists there but isn't a tess checkout — move it aside"
        url = origin_url()
        cloned = False
        if url:
            p = run_ssh(target, login_shell(
                f'GIT_TERMINAL_PROMPT=0 git clone -q {q(url)} "$HOME/tess"'), timeout=300)
            cloned = p.returncode == 0
            how = "cloned"
        if not cloned:
            run_ssh(target, 'rm -rf "$HOME/tess"', timeout=30)
            init = ('git init -q "$HOME/tess" && git -C "$HOME/tess" config '
                    'receive.denyCurrentBranch updateInstead')
            if run_ssh(target, login_shell(init), timeout=60).returncode != 0:
                return False, "couldn't create ~/tess there"
            push = subprocess.run(["git", "-C", TESS_HOME, "push", "-q", f"{target}:tess",
                                   "HEAD:refs/heads/main"], capture_output=True, text=True)
            if push.returncode != 0:
                return False, "couldn't copy tess over: " + (push.stderr.strip().splitlines()
                                                              or ["git push failed"])[-1][:120]
            fix = 'git -C "$HOME/tess" checkout -q main 2>/dev/null; '
            if url:
                fix += f'git -C "$HOME/tess" remote add origin {q(url)} 2>/dev/null; '
            run_ssh(target, login_shell(fix + "true"), timeout=60)
            how = "copied from this machine"
    p = run_ssh(target, login_shell('cd "$HOME/tess" && ./install.sh --minimal >/dev/null 2>&1; '
                                    '"$HOME/.local/bin/tess" --version'), timeout=300)
    v = (p.stdout.strip().splitlines() or [""])[-1]
    if not v.startswith("tess "):
        return False, "installed the files but tess won't run there — try:  tess node setup"
    return True, f"{v} · {how}"


def setup(name, target, quiet_ok=False):
    """Everything on the far side. Returns True when the node is fully usable."""
    f = facts(target)
    if not f.get("home"):
        step(NO, "look around", "the node didn't answer a simple question — try again")
        return False
    good = True
    need = [t for t in ("git", "rsync", "python3") if not f.get("has_" + t)]
    if need:
        good = False
        step(NO, "git · rsync · python3", "missing there: " + ", ".join(need))
    else:
        step(OK, "git · rsync · python3")
    ok, detail = install_dtach(target, f)
    good &= ok
    step(OK if ok else NO, "dtach (persistent shells)", detail)
    ok, detail = install_tess(target, f)
    good &= ok
    step(OK if ok else NO, "tess", detail)
    return good


# ---------------------------------------------------------------- commands

def cmd_add(args):
    flags = {a for a in args if a.startswith("--")}
    args = [a for a in args if not a.startswith("--")]
    unknown = flags - {"--no-setup", "--register-only"}
    if unknown:
        die(f"unknown option {sorted(unknown)[0]}\n  usage: tess node add <name> <user@host> "
            "[--no-setup] [--register-only]", 2)
    name = args[0].lower() if args else ""
    addr = args[1] if len(args) > 1 else ""
    if len(args) > 2:
        die("usage: tess node add <name> <user@host>", 2)
    if not name:
        if not interactive():
            die("usage: tess node add <name> <user@host>\n"
                "  e.g.  tess node add mini me@100.64.0.7     (tess node me, run there, "
                "prints the exact line)", 2)
        print(f"\n  {C.bold}add a node{C.r}  {C.grey}— another machine you work on{C.r}\n")
        name = input("  name it (e.g. mini): ").strip().lower()
    if not NAME_RE.match(name):
        die(f"'{name}' can't be a node name — lowercase letters, digits, . _ - (max 32)", 2)
    if name in reserved():
        die(f"'{name}' is already a tess command — pick another name (e.g. {name}-box)", 2)
    existing = config_peers()
    adopt = alias_defined(name) and not managed_block(name)
    if not addr:
        if adopt or name in existing:
            pass                                    # `tess node add mini` adopts the alias
        elif interactive():
            addr = input("  its address (user@host or user@ip): ").strip()
        if not addr and not (adopt or name in existing):
            die("usage: tess node add <name> <user@host>", 2)

    print(f"\n  {C.bold}{name}{C.r}")
    wrote_block = False
    if addr:
        user, host, port = parse_address(addr)
        if adopt:
            u2, h2, p2 = resolved(name)
            if (h2, u2 or user) != (host, user or u2) or (port and port != p2):
                die(f"~/.ssh/config already has its own 'Host {name}' → {u2}@{h2}.\n"
                    f"  Use a different name, or adopt that one as is:  tess node add {name}")
            step(OK, "ssh alias", f"using your existing Host {name}")
        else:
            had = managed_block(name)
            write_ssh_block(name, user, host, port)
            wrote_block = not had
            step(OK, "ssh alias", f"Host {name} → {(user + '@') if user else ''}{host}"
                 + (f":{port}" if port else ""))
    else:
        u2, h2, _ = resolved(existing.get(name, name))
        step(OK, "ssh alias", f"using your existing Host {name} → {u2}@{h2}")
    target = name if (addr or adopt) else existing.get(name, name)

    def register():
        ps = config_peers()
        ps[name] = target
        write_config_peers(ps)

    if "--register-only" in flags:
        register()
        step(DOT, "registered without contacting it", f"finish with:  tess node setup {name}")
        return 0

    ok, detail = reach(target, name)
    step(OK if ok else NO, "reach it over ssh", detail)
    if not ok:
        if wrote_block:
            remove_ssh_block(name)
        print(f"\n  {C.red}not added{C.r} — nothing was left behind. Fix the above and re-run.\n")
        return 1
    register()
    good = True if "--no-setup" in flags else setup(name, target)
    step(OK, "registered", "TESS_PEERS in ~/.config/tess/config")
    print()
    if good:
        print(f"  {C.green}{name} is ready.{C.r}   {C.cyan}tess {name}{C.r} opens a shell there"
              f" · {C.cyan}tess {name} handoff{C.r} · {C.cyan}tess node{C.r} shows everything\n")
        return 0
    print(f"  {C.yellow}{name} is added, with gaps above.{C.r} Fix them, then:  "
          f"{C.cyan}tess node setup {name}{C.r}\n")
    return 1


def need_node(name):
    ps = peers()
    key = (name or "").lower()
    if key not in ps:
        have = ", ".join(ps) or "none yet"
        die(f"no node named '{name}' ({have}).\n  add one:  tess node add <name> <user@host>", 2)
    return key, ps[key]


def cmd_setup(args):
    if not args:
        die("usage: tess node setup <name>", 2)
    name, target = need_node(args[0])
    print(f"\n  {C.bold}{name}{C.r}")
    ok, detail = reach(target, name)
    step(OK if ok else NO, "reach it over ssh", detail)
    if not ok:
        print()
        return 1
    good = setup(name, target)
    print()
    return 0 if good else 1


def cmd_rm(args):
    if not args:
        die("usage: tess node rm <name>", 2)
    name = args[0].lower()
    ps = config_peers()
    if name not in ps:
        die(f"no node named '{name}' in {CONFIG.replace(HOME, '~')}", 2)
    del ps[name]
    write_config_peers(ps)
    dropped = remove_ssh_block(name)
    print(f"  {C.green}{OK}{C.r} forgot {name}" +
          ("" if dropped else f"  {C.grey}(its Host entry in ~/.ssh/config is yours — left alone){C.r}"))
    print(f"  {C.grey}nothing was touched on the machine itself{C.r}")
    return 0


def my_addresses():
    out = []
    ts = shutil.which("tailscale") or "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    if os.path.exists(ts) or shutil.which("tailscale"):
        try:
            p = subprocess.run([ts, "ip", "-4"], capture_output=True, text=True, timeout=5)
            out += [(l.strip(), "tailscale") for l in p.stdout.splitlines()
                    if re.match(r"^\d+\.\d+\.\d+\.\d+$", l.strip())]
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))                 # no packet is sent; picks the LAN address
        out.append((s.getsockname()[0], "local network"))
        s.close()
    except OSError:
        pass
    return out


def cmd_me(args):
    user = getpass.getuser()
    host = socket.gethostname().split(".")[0].lower()
    guess = re.sub(r"[^a-z0-9-]+", "-", host).strip("-") or "box"
    sshd = False
    try:
        s = socket.create_connection(("127.0.0.1", 22), timeout=1)
        s.close()
        sshd = True
    except OSError:
        pass
    print(f"\n  {C.bold}this machine{C.r}  {C.grey}{user}@{host}{C.r}\n")
    if sshd:
        step(OK, "accepts ssh")
    else:
        step(NO, "ssh is off here",
             "macOS: System Settings → General → Sharing → Remote Login" if sys.platform == "darwin"
             else "install and start openssh-server")
    addrs = my_addresses()
    if not addrs:
        print(f"\n  on the other machine:  {C.cyan}tess node add {guess} {user}@<this machine's address>{C.r}\n")
        return 0
    print("\n  on the other machine, run one of:\n")
    for ip, kind in addrs:
        print(f"    {C.cyan}tess node add {guess} {user}@{ip}{C.r}   {C.grey}{kind}{C.r}")
    print()
    return 0


PROBE = 'T=$(command -v tess 2>/dev/null || ls "$HOME/.local/bin/tess" 2>/dev/null); ' \
        '[ -n "$T" ] && "$T" --version 2>/dev/null || echo "tess -"; echo "---"; python3 - --json'


def probe(item):
    name, target = item
    src = open(os.path.join(HERE, "node_sessions.py")).read()
    p = run_ssh(target, PROBE, timeout=25, stdin_text=src, connect=6)
    info = {"name": name, "target": target, "up": False, "tess": "", "sessions": [], "error": ""}
    head, sep, tail = p.stdout.partition("---")
    if not sep:
        info["error"] = why(p)
        return info
    info["up"] = True
    v = head.strip().splitlines()[-1] if head.strip() else ""
    info["tess"] = "" if v in ("", "tess -") else v.replace("tess ", "", 1)
    try:
        info["sessions"] = json.loads(tail.strip() or "[]")
    except ValueError:
        info["error"] = "couldn't list its shells (python3 missing there?)"
    return info


def cmd_board(args):
    ps = peers()
    as_json = "--json" in args
    if not ps:
        if as_json:
            print("[]")
            return 0
        print(f"\n  {C.bold}nodes{C.r}  {C.grey}— your other machines{C.r}\n\n"
              f"  none yet.\n\n"
              f"  {C.cyan}tess node add <name> <user@host>{C.r}   set one up end to end\n"
              f"  {C.cyan}tess node me{C.r}                       run on the other machine: prints that line\n")
        return 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        infos = list(ex.map(probe, ps.items()))
    if as_json:
        print(json.dumps(infos, indent=2))
        return 0
    mine = local_version().replace("tess ", "", 1)
    w = max(len(n) for n in ps)
    print(f"\n  {C.bold}nodes{C.r}\n")
    for i in infos:
        u, h, _ = resolved(i["target"])
        where = f"{u}@{h}" if u else h
        if not i["up"]:
            print(f"  {C.red}○{C.r} {C.bold}{i['name']:<{w}}{C.r}  {C.grey}{where}{C.r}")
            print(f"    {' ' * w}{C.red}unreachable{C.r} {C.grey}— {i['error']}{C.r}")
            continue
        if not i["tess"]:
            tess = f"{C.yellow}no tess — tess node setup {i['name']}{C.r}"
        elif i["tess"] == mine:
            tess = f"{C.grey}tess {i['tess']}{C.r}"
        else:
            tess = f"{C.yellow}tess {i['tess']} (here: {mine}){C.r}"
        busy = [s for s in i["sessions"] if s["running"]]
        n = len(i["sessions"])
        shells = (f"{n} shell{'s' if n != 1 else ''}"
                  + (f", {len(busy)} running" if busy else "")) if n else "no shells open"
        print(f"  {C.green}●{C.r} {C.bold}{i['name']:<{w}}{C.r}  {C.grey}{where}{C.r}  {tess}  {shells}")
        for s in i["sessions"][:6]:
            what = s["running"][0][:60] if s["running"] else f"{C.grey}idle{C.r}"
            print(f"    {' ' * w}{C.cyan}{s['name']:<10}{C.r} {C.grey}{s['cwd'][:28]:<28}{C.r} {what}")
        if i["error"]:
            print(f"    {' ' * w}{C.yellow}{i['error']}{C.r}")
    first = next((i["name"] for i in infos if i["up"]), next(iter(ps)))
    print(f"\n  {C.cyan}tess {first}{C.r} {C.grey}[name]{C.r} a shell there · "
          f"{C.cyan}tess {first} handoff{C.r} · {C.cyan}tunnel <port>{C.r} · {C.cyan}pull{C.r} · "
          f"{C.cyan}ls{C.r}\n  {C.cyan}tess node add <name> <user@host>{C.r} another · "
          f"{C.cyan}tess help node{C.r}\n")
    return 0


# ---------------------------------------------------------------- tess <node> …

def set_tab(label):
    """Name the terminal tab after the session so a reattached one is findable."""
    if not sys.stdout.isatty():
        return
    if os.environ.get("CMUX_SURFACE_ID") and shutil.which("cmux"):
        subprocess.run(["cmux", "rename-tab", label], capture_output=True)
    sys.stdout.write(f"\033]2;{label}\007")
    sys.stdout.flush()


def sessions(target, flag=""):
    src = open(os.path.join(HERE, "node_sessions.py")).read()
    return run_ssh(target, "python3 - " + flag, timeout=40, stdin_text=src)


def kill_session(target, s):
    if not SESSION_RE.match(s):
        die(f"'{s}' isn't a session name", 2)
    pat = r"dtach -A [^ ]*\.dtach-" + re.escape(s) + r"( |$)"
    p = run_ssh(target, f"pkill -f {q(pat)} && echo killed || echo none", timeout=30)
    if "killed" in p.stdout:
        print(f"  {C.green}{OK}{C.r} ended {s}")
        return 0
    if p.returncode not in (0, 1) and "none" not in p.stdout:
        die(why(p))
    print(f"  no shell named '{s}' there")
    return 1


def attach(name, target, s):
    if not SESSION_RE.match(s):
        die(f"'{s}' can't be a session name — letters, digits, . _ -", 2)
    if not sys.stdin.isatty():
        die(f"`tess {name}` opens an interactive shell — it needs a terminal.\n"
            f"  from a script use:  tess {name} run <command…>", 2)
    term = os.environ.get("TERM") or "xterm-256color"
    color = os.environ.get("COLORTERM") or "truecolor"
    if not re.match(r"^[A-Za-z0-9._+-]+$", term):
        term = "xterm-256color"
    if not re.match(r"^[A-Za-z0-9._+-]+$", color):
        color = "truecolor"
    inner = (
        f'command -v dtach >/dev/null 2>&1 || {{ echo "dtach is missing here — on your machine '
        f'run:  tess node setup {name}"; exit 127; }}; '
        f'infocmp {term} >/dev/null 2>&1 && T={term} || T=xterm-256color; '
        f'TERM=$T COLORTERM={color} TESS_NODE={name} TESS_SESSION={s} MINI_SESSION={s} '
        f'exec dtach -A "$HOME/.dtach-{s}" -r ctrl_l -z "$SHELL" -l')
    set_tab(f"{name}:{s}")
    rc = subprocess.call(["ssh", "-t", "-o", "ConnectTimeout=12", target,
                          'exec "$SHELL" -lc ' + q(inner)])
    set_tab(f"{name}:{s} ·off")
    if rc == 255:
        print(f"{C.red}tess:{C.r} lost {name} (or couldn't reach it). Whatever was running there "
              f"is still running — `tess {name} {s}` reattaches.", file=sys.stderr)
    return rc


def confirm(prompt, word=None, yes=False):
    if yes:
        return True
    if not interactive():
        die("needs confirmation — re-run with --yes", 2)
    got = input(prompt).strip().lower()
    return got == word if word else got in ("y", "yes")


def cmd_on(name, rest):
    name, target = need_node(name)
    verb = rest[0] if rest else ""
    tail = rest[1:]
    yes = "--yes" in tail or "-y" in tail
    tail_plain = [a for a in tail if a not in ("--yes", "-y")]

    if verb in ("ls", "st", "status"):
        p = sessions(target, "--color" if sys.stdout.isatty() else "")
        if p.returncode != 0:
            die(f"{name}: {why(p)}")
        print(p.stdout.rstrip("\n") if p.stdout.strip()
              else f"  no shells open on {name}  {C.grey}(tess {name} opens one){C.r}")
        return 0
    if verb == "kill":
        if not tail_plain:
            die(f"usage: tess {name} kill <session>", 2)
        return max(kill_session(target, s) for s in tail_plain)
    if verb in ("clean", "killall"):
        flag = "--idle" if verb == "clean" else "--names"
        p = sessions(target, flag)
        if p.returncode != 0:
            die(f"{name}: {why(p)}")
        names = p.stdout.split()
        if not names:
            print("  nothing idle" if verb == "clean" else "  no shells open")
            return 0
        if verb == "clean":
            print(f"  idle: {' '.join(names)}")
            if not confirm("  end these? [y/N] ", yes=yes):
                return 1
        else:
            print(sessions(target, "--color" if sys.stdout.isatty() else "").stdout.rstrip("\n"))
            if not confirm(f"  end ALL {len(names)}, running work included? type 'yes': ",
                           word="yes", yes=yes):
                print("  aborted")
                return 1
        for s in names:
            kill_session(target, s)
        return 0
    if verb == "run":
        cmdline = tail[1:] if tail[:1] == ["--"] else tail
        if not cmdline:
            die(f"usage: tess {name} run <command…>", 2)
        script = cmdline[0] if len(cmdline) == 1 else " ".join(q(a) for a in cmdline)
        tty = ["-t"] if sys.stdin.isatty() and sys.stdout.isatty() else []
        return subprocess.call(["ssh"] + tty + ["-o", "ConnectTimeout=12", target,
                                                login_shell(script)])
    if verb == "ssh":
        os.execvp("ssh", ["ssh", "-o", "ConnectTimeout=12", target] + tail)
    if verb in ("handoff", "send"):
        os.execvp(sys.executable, [sys.executable, os.path.join(HERE, "handoff.py"), name] + tail)
    if verb == "back":
        os.execvp(sys.executable, [sys.executable, os.path.join(HERE, "handoff.py"),
                                   "back", name] + tail)
    if verb == "tunnel":
        os.execvp(sys.executable, [sys.executable, os.path.join(HERE, "tunnel.py"), name] + tail)
    if verb in ("pull", "sync"):
        env = dict(os.environ, TESS_NODE_LABEL=name)
        os.execvpe(sys.executable, [sys.executable, os.path.join(HERE, "node_pull.py"),
                                    target] + tail, env)
    if verb == "new":
        os.execvp(TESS_BIN, [TESS_BIN, "new", "--on", name] + tail)
    if verb in ("setup", "check"):
        return cmd_setup([name])
    if verb == "rm":
        return cmd_rm([name])
    if verb.startswith("-"):
        die(f"unknown option '{verb}' — tess help node", 2)
    if len(rest) > 1:
        die(f"'{verb}' isn't something a node does — tess help node\n"
            f"  (a session name is one word:  tess {name} {verb})", 2)
    return attach(name, target, verb or "main")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("ls", "list", "status", "--json"):
        return cmd_board(args)
    head, rest = args[0], args[1:]
    if head in ("-h", "--help", "help"):
        print(__doc__.strip() + "\n")
        return 0
    if head == "on":
        if not rest:
            die("usage: tess <node> [session | ls | handoff | tunnel <port> | pull | …]", 2)
        return cmd_on(rest[0], rest[1:])
    if head == "add":
        return cmd_add(rest)
    if head in ("rm", "remove", "forget"):
        return cmd_rm(rest)
    if head in ("setup", "check", "doctor"):
        return cmd_setup(rest)
    if head == "me":
        return cmd_me(rest)
    if head.lower() in peers():                 # tess node mini … == tess mini …
        return cmd_on(head, rest)
    die(f"'{head}' isn't a node or a node command.\n"
        f"  tess node                          see your nodes\n"
        f"  tess node add <name> <user@host>   add one", 2)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
    except EOFError:
        print()
        sys.exit(1)
    except BrokenPipeError:                     # `tess node | head`
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
