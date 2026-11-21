#!/usr/bin/env python3
"""tess new --on <peer> … — cut a worktree on another machine.

    tess new --on mini fix/thing              the repo you're standing in
    tess new --on mini Mono-icarus fix/thing  that repo by name
    tess new --on mini fix/thing --base dev
    tess new --on mini fix/thing --no-setup   don't install dependencies there
    tess new --on mini fix/thing --dry-run

The peer does the actual work: this resolves the repo and runs that machine's
own `tess new`, so the worktree lands in its configured root, by its rules,
with its own .env files copied in. Then dependencies are installed there,
because a worktree you cannot run isn't finished.

It is deliberately the same grammar as local `tess new` with one flag added, so
there is nothing new to learn: the repo is optional, the feature is last, and an
unknown repo is an error rather than a reinterpretation.
"""
import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_common import C  # noqa: E402
from tess_peers import (PeerError, install_plan, login_shell, q,  # noqa: E402
                        remote_home, remote_tess, resolve_peer,
                        run_remote_install, ssh)


def die(msg, code=1):
    print(f"{C.red}✗{C.r} {msg}", file=sys.stderr)
    sys.exit(code)


def note(msg):
    print(f"  {C.grey}· {msg}{C.r}")


def local_repo_name():
    """The repo we're standing in, if any — so the repo argument can be omitted."""
    top = subprocess.run(["git", "rev-parse", "--path-format=absolute",
                          "--git-common-dir"], capture_output=True, text=True)
    if top.returncode != 0 or not top.stdout.strip():
        return None
    return os.path.basename(os.path.dirname(top.stdout.strip().rstrip("/")))


def main():
    ap = argparse.ArgumentParser(
        prog="tess new --on <peer>", add_help=True,
        description="Cut a worktree on another machine, using that machine's own tess.",
        epilog='peers live in ~/.config/tess/config:  TESS_PEERS="mini=<ssh target>"')
    ap.add_argument("--on", metavar="PEER", required=True, help="peer name")
    ap.add_argument("args", nargs="*", metavar="[<repo>] <feature>")
    ap.add_argument("--base", metavar="BRANCH", help="cut from this branch")
    ap.add_argument("--no-setup", action="store_true",
                    help="don't install dependencies on the peer")
    ap.add_argument("--dry-run", "-n", action="store_true", help="print the plan only")
    args, rest = ap.parse_known_args()
    bad = [a for a in rest if a.startswith("-")]
    if bad:
        ap.error(f"unrecognized arguments: {' '.join(bad)}")
    positional = list(args.args) + rest

    if not positional:
        die("name the feature:  tess new --on {} <feature>".format(args.on))
    if len(positional) > 2:
        die("too many arguments — usage: tess new --on <peer> [<repo>] <feature>\n"
            "  (a base branch goes via --base <branch>)")

    target, err = resolve_peer(args.on)
    if err:
        die(err)

    feature = positional[-1]
    repo = positional[0] if len(positional) == 2 else local_repo_name()
    if not repo:
        die("not inside a repo, so name one:  "
            f"tess new --on {args.on} <repo> {feature}")

    try:
        rhome = remote_home(target)
        rtess = remote_tess(target)
        if not rtess:
            die(f"tess isn't installed on {args.on}.\n"
                f"  Install it there first:  ssh {target} "
                f"'curl -fsSL <tess install> | bash'")

        cmd = f"{rtess} new {repo} {feature}"
        if args.base:
            cmd += f" --base {args.base}"

        print(f"\n{C.bold}cutting a worktree on {args.on}{C.r}")
        print(f"  {C.grey}repo   {C.r}  {repo}")
        print(f"  {C.grey}feature{C.r}  {feature}" +
              (f"  {C.grey}(from {args.base}){C.r}" if args.base else ""))
        print(f"  {C.grey}via    {C.r}  {cmd}")
        if args.dry_run:
            print(f"\n{C.yellow}dry run — nothing touched{C.r}\n")
            return

        # The peer's tess resolves its own repo map and worktree root, so a repo
        # it doesn't have is its error to report, with its own wording.
        # merge stderr: when the peer's tess refuses (unknown repo, unsafe
        # feature name), its own wording is the most useful thing to show
        out = ssh(target, login_shell(cmd) + ' 2>&1', check=False)
        # the peer's tess colours its output; those escapes would end up inside
        # the path we parse out of it
        out = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", out)
        path = ""
        for line in out.splitlines():
            if "Worktrees are in:" in line:
                path = line.split("Worktrees are in:", 1)[1].strip()
        if not path:
            tail = [l for l in out.splitlines() if l.strip()][-6:]
            die(f"{args.on} did not create it:\n    " +
                ("\n    ".join(tail) if tail else "(no output from its tess)"))

        # a single-repo feature puts the repo dir inside the feature root
        repo_dir = f"{path}/{repo}"
        if not ssh(target, f"test -d {q(repo_dir)} && echo y", check=False):
            repo_dir = path
        note(f"created {repo_dir}")

        plan = None
        locks = ssh(target, f"ls -1 {q(repo_dir)} 2>/dev/null", check=False).splitlines()
        plan = install_plan(repo_dir, lockfiles=locks)
        if plan and not args.no_setup:
            run_remote_install(target, repo_dir, plan, args.on, note=note)
        elif plan:
            note(f"skipped dependencies (--no-setup) — run `{plan[0]}` there first")

        print(f"\n{C.green}✓ {args.on} has it.{C.r} Work there with:\n")
        print(f"    {C.bold}ssh -t {target} 'cd {repo_dir} && claude'{C.r}\n")
        print(f"  {C.grey}see its dev server here:  tess tunnel {args.on} <port>{C.r}")
        print(f"  {C.grey}move a running session over:  tess handoff {args.on}{C.r}\n")
    except PeerError as e:
        die(str(e))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
