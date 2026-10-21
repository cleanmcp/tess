#!/usr/bin/env python3
"""tess handoff — move a live coding session between machines, and bring it back.

    tess handoff                      what's here · what each peer is holding
    tess handoff <peer>               send this folder's newest session to <peer>
    tess handoff <peer> --pick        choose any past session first
    tess handoff <peer> --session <id>
    tess handoff back [<peer>]        take back what that peer is holding
    tess handoff <peer> --dry-run     print the plan, touch nothing

A session is three things, and each travels the way that suits it:

  code      one throwaway WIP commit, pushed over ssh to a neutral ref and
            soft-reset on arrival — git moves only the delta, and the working
            tree lands byte-identical, uncommitted edits included
  env       .env* files rsynced beside it (they're gitignored, so no commit
            can carry them)
  context   the agent's transcript, rsynced with every absolute path rewritten
            for the destination's home directory

It is a baton, not a mirror: exactly one machine holds a session at a time. The
source is parked with a marker file, so the two sides can't diverge and there is
no merge step. The transcript is append-only and only the holder appends to it.

Peers are configured, never guessed — in ~/.config/tess/config:

    TESS_PEERS="mini=mac-mini  box=dev@10.0.0.5"

where each entry is <name>=<ssh target> (anything `ssh` accepts: a Host alias
from ~/.ssh/config, user@host, or host). Key-based auth is assumed; a peer that
prompts for a password will hang, so set up a key first.

Portability: needs a POSIX host (macOS or Linux, or WSL on Windows) with ssh,
rsync and git on both ends. Session transcripts are Claude Code's today; the
store is isolated in ClaudeStore so another agent's layout can be added beside
it without touching the transport.
"""
import argparse
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_common import C, short  # noqa: E402

HOME = os.path.expanduser("~")
MARKER = ".tess-handoff"
NEUTRAL = "refs/tess-handoff"      # never a checked-out branch, so pushes always land
WIP_MSG = "tess handoff WIP — soft-reset on arrival, not real history"
SKIP = ["node_modules", ".venv", "venv", "__pycache__", ".turbo", ".next", "dist",
        "build", ".cache", ".pytest_cache", ".local-blob"]


# ---------------------------------------------------------------- plumbing

def die(msg, code=1):
    print(f"{C.red}✗{C.r} {msg}", file=sys.stderr)
    sys.exit(code)


def note(msg):
    print(f"  {C.grey}· {msg}{C.r}")


def run(cmd, cwd=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        tail = (p.stderr or p.stdout).strip().splitlines()[-4:]
        die(f"{shlex.join(cmd[:4])}… failed:\n    " + "\n    ".join(tail))
    return p.stdout.strip()


def ssh(target, script, check=True):
    """Run a POSIX shell snippet on a peer. `script` must already be quoted."""
    return run(["ssh", "-o", "BatchMode=yes", target, script], check=check)


def q(path):
    return shlex.quote(path)


def preflight():
    if os.name == "nt":
        die("handoff needs a POSIX host — run it from WSL on Windows.")
    missing = [t for t in ("ssh", "rsync", "git") if not shutil.which(t)]
    if missing:
        die(f"missing on this machine: {', '.join(missing)}")


def peers():
    """{name: ssh target} from TESS_PEERS (env first, then the config file)."""
    raw = os.environ.get("TESS_PEERS")
    if raw is None:
        cfg = os.path.join(HOME, ".config", "tess", "config")
        try:
            with open(cfg) as fh:
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


def no_peers():
    die("no peers configured. Add one to ~/.config/tess/config:\n\n"
        f'    TESS_PEERS="mini=<ssh target>"\n\n'
        "  where <ssh target> is a Host alias, user@host, or host that `ssh` can\n"
        "  reach with key-based auth (a password prompt would hang).")


def remote_home(target):
    h = ssh(target, 'printf %s "$HOME"', check=False)
    if not h.startswith("/"):
        die(f"couldn't reach '{target}' over ssh (needs key-based auth).\n"
            f"  try:  ssh {target} true")
    return h


def rsync(src, dst, extra=()):
    cmd = ["rsync", "-az", "--partial"]
    for s in SKIP:
        cmd += ["--exclude", s]
    run(cmd + list(extra) + [src, dst])


def map_path(path, src_home, dst_home):
    """Same location relative to $HOME on the other machine."""
    if path == src_home:
        return dst_home
    if not path.startswith(src_home.rstrip("/") + "/"):
        die(f"{path} is outside the home directory, so it has no obvious place on\n"
            f"  the peer. Move the work under {src_home} and retry.")
    return os.path.join(dst_home, os.path.relpath(path, src_home))


# ---------------------------------------------------------------- the session store

class ClaudeStore:
    """Where Claude Code keeps sessions: ~/.claude/projects/<cwd-slug>/<id>.jsonl

    The slug is the working directory with "/" turned into "-", so a transcript
    is only resumable from the folder it was recorded in — which is exactly why
    handoff has to rewrite paths and place the file by the destination's slug.
    """
    name = "claude"
    resume_cmd = "claude --resume {sid}"

    @staticmethod
    def root(home=HOME):
        return os.path.join(home, ".claude", "projects")

    @staticmethod
    def slug(cwd):
        return cwd.replace("/", "-")

    @classmethod
    def sessions(cls):
        out = []
        for f in glob.glob(os.path.join(cls.root(), "*", "*.jsonl")):
            out.append({"sid": os.path.basename(f)[:-6], "path": f,
                        "proj": os.path.basename(os.path.dirname(f)),
                        "mtime": os.path.getmtime(f)})
        return sorted(out, key=lambda s: s["mtime"], reverse=True)

    @classmethod
    def transcript_for(cls, home, cwd, sid):
        return os.path.join(cls.root(home), cls.slug(cwd), sid + ".jsonl")

    @staticmethod
    def describe(sess):
        """Title + the folder it is in now.

        A session can move folders mid-run (each entry records its own cwd), so
        the LAST cwd is where it actually is; the FIRST title is what it is about.
        """
        cwd = title = first = None
        try:
            with open(sess["path"], errors="ignore") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    if d.get("aiTitle") and not title:
                        title = d["aiTitle"]
                    if d.get("cwd"):
                        cwd = d["cwd"]
                    if not first and d.get("type") == "user":
                        c = (d.get("message") or {}).get("content")
                        if isinstance(c, str):
                            first = c
                        elif isinstance(c, list):
                            first = next((b.get("text") for b in c if isinstance(b, dict)
                                          and b.get("type") == "text"), None)
        except OSError:
            pass
        label = re.sub(r"<[^>]+>", " ", title or first or "(no prompt yet)")
        sess.update(cwd=cwd, label=short(label, 68))
        return sess


STORE = ClaudeStore


def ago(ts):
    s = max(0, int(time.time() - ts))
    for n, u in ((86400, "d"), (3600, "h"), (60, "m")):
        if s >= n:
            return f"{s // n}{u}"
    return f"{s}s"


def session_for_cwd(cwd):
    """Newest session recorded in this folder, or the nearest ancestor of it."""
    alls = STORE.sessions()
    probe = os.path.realpath(cwd)
    while True:
        hit = [s for s in alls if s["proj"] == STORE.slug(probe)]
        if hit:
            return STORE.describe(hit[0])
        parent = os.path.dirname(probe)
        if parent == probe or len(probe) <= len(HOME):
            return None
        probe = parent


def pick(sessions, prompt):
    """Interactive chooser. Never prompts when stdin isn't a TTY (agent-safe)."""
    sessions = [STORE.describe(s) for s in sessions[:20]]
    if not sessions:
        die("no sessions found on this machine")
    if not sys.stdin.isatty():
        lines = "\n".join(f"    {s['sid']}  {s['label']}" for s in sessions[:10])
        die("not a terminal, so there's nothing to pick with. Name one:\n"
            f"  --session <id>\n\n{lines}")
    print(f"\n{C.bold}{prompt}{C.r}\n")
    for i, s in enumerate(sessions, 1):
        where = (s["cwd"] or "?").replace(HOME, "~")
        print(f"  {C.bold}{i:2}{C.r} {C.grey}{ago(s['mtime']):>4} ago{C.r}  {s['label']}")
        print(f"     {C.grey}{where}{C.r}")
    try:
        ans = input("\nnumber (Enter cancels): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(130)
    if not ans:
        sys.exit(0)
    if not ans.isdigit() or not 1 <= int(ans) <= len(sessions):
        die("not one of the listed numbers")
    return sessions[int(ans) - 1]


def session_by_id(sid):
    for s in STORE.sessions():
        if s["sid"] == sid or s["sid"].startswith(sid):
            return STORE.describe(s)
    die(f"no session here with id '{sid}'")


# ---------------------------------------------------------------- git

def git_context(cwd):
    """The worktree holding `cwd`, its branch, and the repo it was cut from."""
    top = run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], check=False)
    if not top:
        return None
    branch = run(["git", "-C", top, "branch", "--show-current"])
    if not branch:
        die("that folder is on a detached HEAD — check out a branch before handing off.")
    common = run(["git", "-C", top, "rev-parse", "--path-format=absolute",
                  "--git-common-dir"])
    central = os.path.dirname(common.rstrip("/"))
    parent = os.path.dirname(top)
    # tess layout: <worktree root>/<feature>/<repo>. A single-repo feature is the
    # repo dir itself, so fall back to the folder's own name.
    feature = os.path.basename(parent) if parent != os.path.dirname(central) \
        else os.path.basename(top)
    return {"top": top, "branch": branch, "central": central,
            "repo": os.path.basename(central), "feature": feature}


def wip_commit(top, remote=None):
    """Park every uncommitted change in one commit. Returns True if it made one."""
    if remote:
        target, path = remote
        if not ssh(target, f"git -C {q(path)} status --porcelain"):
            return False
        ssh(target, f"git -C {q(path)} add -A && git -C {q(path)} "
                    f"-c user.name=tess -c user.email=tess@localhost "
                    f"commit --no-verify -q -m {q(WIP_MSG)}")
        return True
    if not run(["git", "-C", top, "status", "--porcelain"]):
        return False
    run(["git", "-C", top, "add", "-A"])
    run(["git", "-C", top, "-c", "user.name=tess", "-c", "user.email=tess@localhost",
         "commit", "--no-verify", "-q", "-m", WIP_MSG])
    return True


def unwip(top, remote=None):
    """Undo the WIP commit, leaving the working tree dirty exactly as it was."""
    if remote:
        target, path = remote
        ssh(target, f"git -C {q(path)} reset --soft HEAD~1")
    else:
        run(["git", "-C", top, "reset", "--soft", "HEAD~1"])


# ---------------------------------------------------------------- markers

def marker_roots():
    """Where to look for parked sessions — from config, never hardcoded."""
    roots = [os.environ.get("TESS_WORKTREE_ROOT") or os.path.join(HOME, "worktrees"),
             os.environ.get("TESS_CORE") or ""]
    roots += (os.environ.get("TESS_REPO_DIRS") or "").split()
    return [os.path.expanduser(r) for r in roots if r and os.path.isdir(os.path.expanduser(r))]


def parked():
    """Every folder on this machine currently handed out, with its marker."""
    out = []
    for root in marker_roots():
        base_depth = root.rstrip("/").count(os.sep)
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP and d != ".git"
                       and base.count(os.sep) - base_depth < 3]
            if MARKER in files:
                try:
                    with open(os.path.join(base, MARKER)) as fh:
                        out.append((base, json.load(fh)))
                except (OSError, ValueError):
                    continue
    return out


def park(cwd, peer, sess, landed):
    with open(os.path.join(cwd, MARKER), "w") as fh:
        json.dump({"peer": peer, "store": STORE.name, "sid": sess["sid"],
                   "label": sess["label"], "landed_at": landed,
                   "at": time.strftime("%Y-%m-%d %H:%M")}, fh, indent=2)


def unpark(cwd):
    try:
        os.remove(os.path.join(cwd, MARKER))
    except OSError:
        pass


# ---------------------------------------------------------------- transcript

def move_transcript(sid, src_path, src_home, dst_home, dst_cwd, to=None, frm=None):
    """Place the transcript where the destination will look for it.

    Rewrites absolute paths so the recorded cwd matches the destination, then
    writes it under the destination's project slug.
    """
    tmp = tempfile.mkdtemp(prefix="tess-handoff-")
    staged = os.path.join(tmp, sid + ".jsonl")
    try:
        if frm:
            rsync(f"{frm}:{src_path}", staged)
        else:
            shutil.copyfile(src_path, staged)
        if src_home != dst_home:
            with open(staged, errors="ignore") as fh:
                body = fh.read()
            with open(staged, "w") as fh:
                fh.write(body.replace(src_home, dst_home))

        dst_dir = os.path.join(STORE.root(dst_home), STORE.slug(dst_cwd))
        if to:
            ssh(to, f"mkdir -p {q(dst_dir)}")
            rsync(staged, f"{to}:{dst_dir}/")
            sib = src_path[:-6]
            if os.path.isdir(sib):            # subagent logs + tool results
                rsync(sib + "/", f"{to}:{os.path.join(dst_dir, sid)}/")
        else:
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copyfile(staged, os.path.join(dst_dir, sid + ".jsonl"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- send

def send(name, target, sess, dry):
    cwd = sess.get("cwd")
    if not cwd or not os.path.isdir(cwd):
        die(f"that session's folder is gone ({cwd or 'unknown'}) — nothing to hand off")
    if os.path.exists(os.path.join(cwd, MARKER)):
        with open(os.path.join(cwd, MARKER)) as fh:
            held = json.load(fh)
        die(f"{cwd.replace(HOME, '~')} is already handed off to "
            f"{held['peer']} (since {held['at']}).\n  Take it back first:  tess handoff back "
            f"{held['peer']}")

    rhome = remote_home(target)
    g = git_context(cwd)
    dst_cwd = map_path(cwd, HOME, rhome)

    print(f"\n{C.bold}handing off → {name}{C.r}")
    print(f"  {C.grey}session{C.r}  {sess['label']}")
    print(f"  {C.grey}folder {C.r}  {cwd.replace(HOME, '~')}  {C.grey}→{C.r}  {dst_cwd}")
    if g:
        print(f"  {C.grey}git    {C.r}  {g['repo']} @ {g['branch']} "
              f"{C.grey}(delta push over ssh){C.r}")
    if dry:
        print(f"\n{C.yellow}dry run — nothing touched{C.r}\n")
        return

    if g:
        rtop = map_path(g["top"], HOME, rhome)
        ref = f"{NEUTRAL}/{g['branch']}"
        had = wip_commit(g["top"])
        try:
            exists = ssh(target, f"test -d {q(rtop)}/.git -o -f {q(rtop)}/.git && echo y",
                         check=False)
            if exists:
                note(f"pushing {g['branch']} to the worktree there")
                run(["git", "-C", g["top"], "push", "-q", "--force",
                     f"{target}:{rtop}", f"HEAD:{ref}"])
            else:
                rcentral = map_path(g["central"], HOME, rhome)
                if not ssh(target, f"test -d {q(rcentral)} && echo y", check=False):
                    die(f"{g['repo']} isn't on {name} at {rcentral}.\n"
                        f"  Clone it there first, then retry.")
                note(f"pushing {g['branch']} to {g['repo']}")
                run(["git", "-C", g["top"], "push", "-q", "--force",
                     f"{target}:{rcentral}", f"HEAD:{ref}"])
                note(f"creating the worktree on {name} (tess new {g['repo']} {g['feature']})")
                tess_remote = ssh(target, 'sh -lc "command -v tess"', check=False)
                if not tess_remote:
                    die(f"tess isn't installed on {name}, so the worktree can't be created.\n"
                        f"  Install it there, or run:  ssh {target} 'tess new {g['repo']} "
                        f"{g['feature']}'")
                create = f"{tess_remote} new {g['repo']} {g['feature']}"
                ssh(target, f"sh -lc {q(create)}", check=False)
                if not ssh(target, f"test -d {q(rtop)} && echo y", check=False):
                    die(f"couldn't create {rtop} on {name}.\n"
                        f"  Run `tess new {g['repo']} {g['feature']}` there, then retry.")
            # move that worktree onto the branch and the pushed content. tess names
            # a new branch after the feature, which may not be this session's branch.
            ssh(target, f"git -C {q(rtop)} checkout -q -B {q(g['branch'])} {q(ref)} && "
                        f"git -C {q(rtop)} reset -q --hard {q(ref)}")
            if had:
                unwip(None, remote=(target, rtop))
        finally:
            if had:
                unwip(g["top"])          # this side goes back to being dirty

        envs = [f for f in os.listdir(g["top"]) if f.startswith(".env")]
        if envs:
            note(f"{len(envs)} .env file(s)")
            rsync(g["top"] + "/", f"{target}:{rtop}/",
                  extra=["--include", ".env*", "--exclude", "*", "--no-recursive"])
    else:
        nested = [d for d in sorted(os.listdir(cwd))
                  if os.path.exists(os.path.join(cwd, d, ".git"))]
        if nested:
            die(f"{cwd.replace(HOME, '~')} isn't a repo — it holds {', '.join(nested)}.\n"
                f"  Hand off one repo at a time: cd into it first.")
        note("not a repo — rsyncing the folder")
        ssh(target, f"mkdir -p {q(os.path.dirname(dst_cwd))}")
        rsync(cwd + "/", f"{target}:{dst_cwd}/")

    note(f"context ({os.path.getsize(sess['path']) // 1024} KB)")
    move_transcript(sess["sid"], sess["path"], HOME, rhome, dst_cwd, to=target)
    park(cwd, name, sess, dst_cwd)

    resume = STORE.resume_cmd.format(sid=sess["sid"])
    print(f"\n{C.green}✓ {name} has it.{C.r} Pick it up there:\n")
    print(f"    {C.bold}ssh -t {target} 'cd {dst_cwd} && {resume}'{C.r}\n")
    print(f"  {C.grey}bring it back with:  tess handoff back {name}{C.r}\n")


# ---------------------------------------------------------------- take back

def take_back(name, target, dry, want_pick):
    held = [(d, h) for d, h in parked() if h.get("peer") == name]
    if not held:
        die(f"nothing here is handed off to {name}.\n"
            f"  `tess handoff` lists what is parked.")
    if len(held) > 1 or want_pick:
        if not sys.stdin.isatty():
            die("more than one session is out there. Run this in a terminal, or cd "
                "into the folder you want back.")
        print(f"\n{C.bold}{name} is holding:{C.r}\n")
        for i, (d, h) in enumerate(held, 1):
            print(f"  {C.bold}{i:2}{C.r}  {h.get('label', h['sid'])}")
            print(f"      {C.grey}{d.replace(HOME, '~')} · sent {h['at']}{C.r}")
        ans = input("\nnumber (Enter cancels): ").strip()
        if not ans:
            sys.exit(0)
        if not ans.isdigit() or not 1 <= int(ans) <= len(held):
            die("not one of the listed numbers")
        local_cwd, h = held[int(ans) - 1]
    else:
        local_cwd, h = held[0]

    rhome = remote_home(target)
    rtop = h["landed_at"]
    print(f"\n{C.bold}taking back ← {name}{C.r}")
    print(f"  {C.grey}session{C.r}  {h.get('label', h['sid'])}")
    print(f"  {C.grey}folder {C.r}  {rtop}  {C.grey}→{C.r}  {local_cwd.replace(HOME, '~')}")
    if dry:
        print(f"\n{C.yellow}dry run — nothing touched{C.r}\n")
        return

    g = git_context(local_cwd)
    if g:
        had = wip_commit(None, remote=(target, rtop))
        try:
            note(f"fetching {g['branch']} back")
            run(["git", "-C", g["top"], "fetch", "-q", f"{target}:{rtop}", "HEAD"])
            run(["git", "-C", g["top"], "reset", "-q", "--hard", "FETCH_HEAD"])
            if had:
                unwip(g["top"])
        finally:
            if had:
                unwip(None, remote=(target, rtop))
        rsync(f"{target}:{rtop}/", g["top"] + "/",
              extra=["--include", ".env*", "--exclude", "*", "--no-recursive"])
    else:
        note("not a repo — rsyncing the folder back")
        rsync(f"{target}:{rtop}/", local_cwd + "/")

    note("context")
    src_path = STORE.transcript_for(rhome, rtop, h["sid"])
    move_transcript(h["sid"], src_path, rhome, HOME, local_cwd, frm=target)
    unpark(local_cwd)

    resume = STORE.resume_cmd.format(sid=h["sid"])
    print(f"\n{C.green}✓ back on this machine.{C.r} Pick it up:\n")
    print(f"    {C.bold}cd {local_cwd.replace(HOME, '~')} && {resume}{C.r}\n")


# ---------------------------------------------------------------- status

def status(ps):
    print(f"\n{C.bold}handoff{C.r}")
    if ps:
        print("  " + C.grey + "peers: " + " · ".join(f"{k} → {v}" for k, v in ps.items()) + C.r)
    else:
        print(f"  {C.yellow}no peers configured{C.r} "
              f"{C.grey}(TESS_PEERS=\"mini=<ssh target>\" in ~/.config/tess/config){C.r}")
    out = parked()
    print()
    if out:
        for d, h in out:
            print(f"  {C.yellow}→ {h['peer']}{C.r}  {h.get('label', h['sid'])}")
            print(f"    {C.grey}{d.replace(HOME, '~')} · sent {h['at']}{C.r}")
        print(f"\n  {C.grey}take one back:  tess handoff back <peer>{C.r}")
    else:
        print(f"  {C.grey}nothing handed off right now{C.r}")
        here = session_for_cwd(os.getcwd())
        if here and ps:
            print(f"\n  {C.grey}this folder's newest session:{C.r} {here['label']}")
            print(f"  {C.grey}send it:  tess handoff {next(iter(ps))}{C.r}")
    print()


# ---------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(
        prog="tess handoff", add_help=True,
        description="Move a live coding session (context + folder + uncommitted work) "
                    "between machines, and bring it back.",
        epilog='peers live in ~/.config/tess/config:  TESS_PEERS="mini=<ssh target>"')
    ap.add_argument("peer", nargs="?", help="peer name, or 'back' to take one back")
    ap.add_argument("which", nargs="?", help="with 'back': which peer")
    ap.add_argument("--pick", "-p", action="store_true", help="choose the session from a list")
    ap.add_argument("--session", "-s", metavar="ID", help="hand off this session id")
    ap.add_argument("--dry-run", "-n", action="store_true", help="print the plan only")
    args = ap.parse_args()

    ps = peers()
    if not args.peer or args.peer in ("status", "list", "ls"):
        return status(ps)          # --help and status never touch anything

    preflight()
    if not ps:
        no_peers()

    if args.peer in ("back", "here", "pull", "home"):
        name = (args.which or next(iter(ps))).lower()
        if name not in ps:
            die(f"unknown peer '{name}' — configured: {', '.join(ps) or 'none'}")
        return take_back(name, ps[name], args.dry_run, args.pick)

    name = args.peer.lower()
    if name not in ps:
        die(f"unknown peer '{name}' — configured: {', '.join(ps) or 'none'}\n"
            f'  add it:  TESS_PEERS="{name}=<ssh target>"  in ~/.config/tess/config')

    if args.session:
        sess = session_by_id(args.session)
    elif args.pick:
        sess = pick(STORE.sessions(), "hand off which session?")
    else:
        sess = session_for_cwd(os.getcwd())
        if not sess:
            print(f"{C.yellow}no session recorded for this folder.{C.r}")
            sess = pick(STORE.sessions(), "hand off which session?")
    return send(name, ps[name], sess, args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
