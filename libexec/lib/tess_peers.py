"""Shared plumbing for the commands that work across machines.

A peer is another machine you work on: `tess handoff` moves a session to one,
`tess tunnel` reaches one's localhost, `tess new --on` cuts a worktree on one.
They all read the same setting, so it is defined once here.

    TESS_PEERS="mini=mac-mini  box=dev@10.0.0.5"     # ~/.config/tess/config

Each entry is <name>=<ssh target>, where the target is anything ssh accepts: a
Host alias from ~/.ssh/config, user@host, or host. Key-based auth is assumed —
a peer that prompts for a password would hang a non-interactive command.
"""
import os
import re
import shlex
import shutil
import subprocess
import sys

HOME = os.path.expanduser("~")
CONFIG = os.path.join(HOME, ".config", "tess", "config")


# ---------------------------------------------------------------- peers

def peers():
    """{name: ssh target} from TESS_PEERS — the environment first, then config.

    bin/tess exports it, so the env wins; reading the file too keeps these
    helpers usable when run directly (and in tests that override HOME).
    """
    raw = os.environ.get("TESS_PEERS")
    if raw is None:
        try:
            with open(CONFIG) as fh:
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


def no_peers_message(example="mini"):
    return ('no peers configured. Add one to ~/.config/tess/config:\n\n'
            f'    TESS_PEERS="{example}=<ssh target>"\n\n'
            '  where <ssh target> is a Host alias, user@host, or host that ssh can\n'
            '  reach with key-based auth (a password prompt would hang).')


def resolve_peer(name, ps=None):
    """(name, target) or an error string explaining what to do."""
    ps = peers() if ps is None else ps
    if not ps:
        return None, no_peers_message(name or "mini")
    key = (name or "").lower()
    if key not in ps:
        return None, (f"unknown peer '{name}' — configured: {', '.join(ps)}\n"
                      f'  add it:  TESS_PEERS="{key}=<ssh target>"  in {CONFIG}')
    return ps[key], None


# ---------------------------------------------------------------- ssh

def q(path):
    return shlex.quote(path)


def have(*tools):
    """Which of these are missing on this machine."""
    return [t for t in tools if not shutil.which(t)]


def ssh(target, script, check=True):
    """Run a POSIX shell snippet on a peer. Returns stdout, stripped."""
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", target, script],
                       capture_output=True, text=True)
    if check and p.returncode != 0:
        tail = (p.stderr or p.stdout).strip().splitlines()[-4:]
        raise PeerError("\n    ".join(["ssh failed:"] + tail))
    return p.stdout.strip()


class PeerError(RuntimeError):
    pass


def remote_home(target):
    h = ssh(target, 'printf %s "$HOME"', check=False)
    if not h.startswith("/"):
        raise PeerError(f"couldn't reach '{target}' over ssh (needs key-based auth).\n"
                        f"  try:  ssh {target} true")
    return h


def remote_tess(target):
    """Find tess on a peer.

    A non-interactive ssh shell reads neither ~/.zshrc nor ~/.bashrc, so PATH
    there is minimal and a plain `command -v tess` comes back empty on a machine
    that has it. Ask the login shell first, then PATH, then where installers put it.
    """
    probe = ('{ "$SHELL" -lic "command -v tess" 2>/dev/null; '
             'command -v tess 2>/dev/null; '
             'ls "$HOME/.local/bin/tess" 2>/dev/null; } | head -1')
    found = ssh(target, probe, check=False)
    return found.splitlines()[0].strip() if found else ""


def map_path(path, src_home, dst_home):
    """The same location relative to $HOME on the other machine."""
    if path == src_home:
        return dst_home
    if not path.startswith(src_home.rstrip("/") + "/"):
        raise PeerError(f"{path} is outside the home directory, so it has no obvious\n"
                        f"  place on the peer. Move the work under {src_home} and retry.")
    return os.path.join(dst_home, os.path.relpath(path, src_home))


# ---------------------------------------------------------------- dependencies

# Dependencies never travel between machines: node_modules and friends are
# gigabytes of platform-specific build output. The peer installs its own,
# detected from the lockfile the repo actually commits.
INSTALLERS = [
    ("pnpm-lock.yaml", "pnpm install --frozen-lockfile", "node_modules"),
    ("bun.lockb", "bun install --frozen-lockfile", "node_modules"),
    ("bun.lock", "bun install --frozen-lockfile", "node_modules"),
    ("yarn.lock", "yarn install --immutable", "node_modules"),
    ("package-lock.json", "npm ci", "node_modules"),
    ("uv.lock", "uv sync", ".venv"),
    ("poetry.lock", "poetry install", ".venv"),
    ("Cargo.lock", "cargo fetch", "target"),
    ("go.sum", "go mod download", ""),
    ("Gemfile.lock", "bundle install", ""),
]


def install_plan(top, lockfiles=None):
    """(command, dir-it-creates) for this project, or None if we don't know one.

    `lockfiles` lets a caller pass a listing it already has (a peer's, say)
    instead of touching the local disk. TESS_HANDOFF_SETUP overrides both; set
    it empty to turn the step off entirely.
    """
    override = os.environ.get("TESS_HANDOFF_SETUP")
    if override is not None:
        return (override.strip(), "") if override.strip() else None
    for lock, cmd, creates in INSTALLERS:
        if lockfiles is not None:
            if lock in lockfiles:
                return cmd, creates
        elif os.path.exists(os.path.join(top, lock)):
            return cmd, creates
    return None


def login_shell(script):
    """Wrap a command so a peer's real PATH applies.

    `-l` alone is not enough: zsh reads .zshenv/.zprofile/.zlogin for a login
    shell but only reads .zshrc when interactive, and bash likewise only reads
    .bashrc when interactive — which is exactly where version managers (fnm,
    nvm, pyenv, rbenv) put themselves. So ask for an interactive login shell,
    or a tool installed by one of those is simply not found.
    """
    return f'$SHELL -lic {q(script)}'


def run_remote_install(target, rtop, plan, label, note=print):
    """Install dependencies on a peer, with that machine's real PATH."""
    cmd, creates = plan
    if creates and ssh(target, f"test -d {q(os.path.join(rtop, creates))} && echo y",
                       check=False):
        note(f"dependencies already there on {label}")
        return True
    note(f"installing dependencies on {label} ({cmd}) — this one is slow")
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", target,
                        login_shell(f"cd {q(rtop)} && {cmd}")],
                       capture_output=True, text=True)
    if p.returncode != 0:
        tail = (p.stderr or p.stdout).strip().splitlines()[-3:]
        note("! dependencies did not install")
        for t in tail:
            note(f"  {t}")
        note(f"finish it there:  ssh {target} 'cd {rtop} && {cmd}'")
        return False
    return True
