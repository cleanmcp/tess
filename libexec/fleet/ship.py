#!/usr/bin/env python3
# tess ship <feat> [--merge] [--dry-run] — collect a finished feature and ship:
#   per repo worktree: show what changed vs the base branch → run tests
#   (TESS_TEST_CMD, if set) → push the branch → open a PR (gh) → optionally
#   merge (--merge = squash). Stops that repo cleanly on any failed step.
#   Uncommitted changes block shipping (commit or stash first).
#
# tess spend — spend/role ledger: budgets given at spawn + who's capped.
import functools
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
print = functools.partial(print, flush=True)
from tess_agents import list_agents

WORKTREE_ROOT = (os.environ.get("TESS_WORKTREE_ROOT") or os.path.expanduser("~/worktrees")).rstrip("/")
BASE = os.environ.get("TESS_MAIN_BRANCH") or "main"
TEST_CMD = os.environ.get("TESS_TEST_CMD", "")
BUDGETS = os.path.expanduser("~/.config/tess/state/budgets.json")


def die(msg, code=1):
    print(f"tess: {msg}", file=sys.stderr)
    sys.exit(code)


def sh(rdir, *cmd, capture=True):
    return subprocess.run(cmd, cwd=rdir, capture_output=capture, text=True)


def cmd_ship(args):
    dry = "--dry-run" in args
    merge = "--merge" in args
    pos = [a for a in args if not a.startswith("-")]
    if len(pos) != 1:
        die("usage: tess ship <feature> [--merge] [--dry-run]")
    feat = pos[0]
    fdir = os.path.join(WORKTREE_ROOT, feat)
    if not os.path.isdir(fdir):
        die(f"no feature '{feat}' (see: tess ls)")

    repos = [r for r in sorted(os.listdir(fdir))
             if os.path.exists(os.path.join(fdir, r, ".git"))]
    if not repos:
        die(f"'{feat}' has no worktrees")

    shipped, skipped, failed = [], [], []
    for repo in repos:
        rdir = os.path.join(fdir, repo)
        print(f"\n== {repo} ==")
        base = BASE
        r = sh(rdir, "git", "rev-parse", "--verify", "-q", f"origin/{base}")
        base_ref = f"origin/{base}" if r.returncode == 0 else base

        if sh(rdir, "git", "status", "--porcelain").stdout.strip():
            print("  ✗ uncommitted changes — commit or stash first; skipping")
            failed.append(repo)
            continue
        ahead = sh(rdir, "git", "rev-list", "--count", f"{base_ref}..HEAD").stdout.strip()
        if ahead in ("", "0"):
            print(f"  nothing to ship (no commits ahead of {base_ref})")
            skipped.append(repo)
            continue
        print(f"  {ahead} commit(s) ahead of {base_ref}:")
        print("  " + sh(rdir, "git", "diff", "--stat", f"{base_ref}...HEAD")
              .stdout.strip().replace("\n", "\n  "))

        if dry:
            steps = [f"run tests: {TEST_CMD}" if TEST_CMD else "tests: (TESS_TEST_CMD unset — skipped)",
                     f"push branch {feat}", "open PR via gh" + (" + squash-merge" if merge else "")]
            for s in steps:
                print(f"  would {s}")
            shipped.append(repo)
            continue

        if TEST_CMD:
            print(f"  running tests: {TEST_CMD}")
            t = subprocess.run(TEST_CMD, shell=True, cwd=rdir)
            if t.returncode != 0:
                print(f"  ✗ tests FAILED (exit {t.returncode}) — not shipping {repo}")
                failed.append(repo)
                continue
            print("  ✓ tests passed")
        else:
            print("  tests: TESS_TEST_CMD unset — skipping (set it in ~/.config/tess/config)")

        p = sh(rdir, "git", "push", "-u", "origin", "HEAD")
        if p.returncode != 0:
            print(f"  ✗ push failed: {(p.stderr or p.stdout).strip()[:200]}")
            failed.append(repo)
            continue
        print("  ✓ pushed")

        try:
            pr = sh(rdir, "gh", "pr", "create", "--fill", "--base", base)
        except FileNotFoundError:
            print("  ⚠ pushed, but the GitHub CLI isn't installed — open the PR yourself (brew install gh)")
            shipped.append(repo)
            continue
        if pr.returncode == 0:
            url = pr.stdout.strip().splitlines()[-1] if pr.stdout.strip() else ""
            print(f"  ✓ PR: {url}")
            if merge:
                m = sh(rdir, "gh", "pr", "merge", "--squash", "--delete-branch=false")
                print("  ✓ squash-merged" if m.returncode == 0
                      else f"  ✗ merge failed: {(m.stderr or m.stdout).strip()[:200]}")
        else:
            err = (pr.stderr or pr.stdout).strip()
            if "already exists" in err:
                print("  ✓ PR already open")
            else:
                print(f"  ⚠ pushed, but PR not created ({err.splitlines()[0][:120] if err else 'gh failed'})")
        shipped.append(repo)

    print(f"\nship {feat}: {len(shipped)} shipped, {len(skipped)} empty, {len(failed)} failed"
          + (" [DRY RUN]" if dry else ""))
    if not failed and not dry:
        print(f"when merged: tess done {feat} --yes")
    if failed:
        sys.exit(1)


def cmd_spend(args):
    try:
        data = json.load(open(BUDGETS))
    except (OSError, ValueError):
        data = {}
    alive = {a["name"] for a in list_agents()}
    if not data:
        print("no budgets recorded. Cap an agent at spawn: tess claude <feat> \"…\" --budget 5")
        return
    total = 0.0
    for name, d in sorted(data.items()):
        b = d.get("budget_usd")
        mark = "●" if name in alive else "○"
        cap = f"cap ${b}" if b else "no cap"
        if b:
            try:
                total += float(b)
            except ValueError:
                pass
        print(f" {mark} {name:<18} {d.get('tool','?'):<7} {d.get('model') or '(default model)':<24}"
              f" {cap:<10} since {d.get('started','?')}")
    print(f"\nmax authorized across capped agents: ${total:g}"
          "  (caps are enforced by claude --max-budget-usd at spawn)")


def main():
    args = sys.argv[1:]
    if not args:
        die("usage: ship.py ship|spend …")
    sub = args.pop(0)
    if sub == "ship":
        cmd_ship(args)
    elif sub == "spend":
        cmd_spend(args)
    else:
        die(f"unknown subcommand '{sub}'")


if __name__ == "__main__":
    main()
