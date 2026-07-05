#!/usr/bin/env python3
# tess done <feat> [--dry-run] [--yes] — one-shot feature teardown:
# kill the feature's agents (closes their cmux panes), remove its worktrees,
# sweep the folder shell. ONLY touches agents working inside that feature dir.
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _tess_agents import agents_under, hcom

WORKTREE_ROOT = os.environ.get("TESS_WORKTREE_ROOT") or os.path.expanduser("~/worktrees")
TESS_BIN = os.environ.get("TESS_BIN") or os.path.dirname(os.path.realpath(__file__))


def die(msg, code=1):
    print(f"tess done: {msg}", file=sys.stderr)
    sys.exit(code)


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    yes = "--yes" in args or "-y" in args
    pos = [a for a in args if not a.startswith("-")]
    if len(pos) != 1:
        die("usage: tess done <feature> [--dry-run] [--yes]")
    feat = pos[0]
    fdir = os.path.join(WORKTREE_ROOT, feat)
    if not os.path.isdir(fdir):
        die(f"no feature '{feat}' at {fdir} (see: tess ls)")

    agents = agents_under(fdir)
    dirty = []
    for repo in sorted(os.listdir(fdir)):
        rdir = os.path.join(fdir, repo)
        if not os.path.exists(os.path.join(rdir, ".git")):
            continue
        r = subprocess.run(["git", "-C", rdir, "status", "--porcelain"],
                           capture_output=True, text=True)
        if r.stdout.strip():
            dirty.append(repo)

    print(f"tearing down '{feat}':")
    for a in agents:
        print(f"  kill agent {a['name']}  ({a.get('status')}, {a.get('directory')})")
    if not agents:
        print("  (no agents running in it)")
    print(f"  remove worktrees + folder: {fdir}")
    if dirty:
        print(f"  ⚠ UNCOMMITTED changes in: {', '.join(dirty)} — they will be LOST")
    if dry:
        print("(dry run — nothing done)")
        return

    if not yes:
        if sys.stdin.isatty():
            a = input("proceed? [y/N] ").strip().lower()
            if a != "y":
                print("aborted.")
                return
        else:
            die("non-interactive: add --yes to confirm teardown "
                + ("(NOTE the uncommitted changes above!)" if dirty else ""))

    for a in agents:
        r = hcom("kill", a["name"])
        ok = r.returncode == 0
        print(f"  {'✓' if ok else '✗'} killed {a['name']}" + ("" if ok else f" — {r.stderr.strip()[:120]}"))
    r = subprocess.run(["bash", os.path.join(TESS_BIN, "worktree.sh"), "rm", feat])
    if r.returncode != 0:
        die(f"worktree removal had trouble — check: tess ls", r.returncode)
    print(f"✓ '{feat}' done and gone.")


if __name__ == "__main__":
    main()
