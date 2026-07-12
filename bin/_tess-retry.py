#!/usr/bin/env python3
# tess retry <agent> [--dry-run] [--yes] [--model M] [--effort E] [--prompt P]
#            [--readonly] [--auto] [--can-deploy] [--budget N]
#
# Re-run a dead or failed agent in the same worktree with the same prompt,
# tool, model, and any role flags — the natural "recover from failure" button.
#
# What is recovered automatically:
#   tool        from hcom list (claude / kimi)
#   worktree    from hcom list (the agent's working directory)
#   tag         from hcom list
#   model       from ~/.config/tess/state/budgets.json (stored at spawn time)
#   budget cap  from budgets.json (if a cap was set)
#   prompt      the FIRST user message in the transcript (the original task)
#
# Role flags (--readonly / --auto / --can-deploy) are NOT stored at spawn time
# and must be re-supplied if you need them again.  --model / --effort / --prompt
# override the recovered values.
#
# The old (dead/registered) agent is killed first so a fresh name registers
# cleanly in the same tag group.  --yes skips the confirmation prompt.
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _tess_agents import hcom, list_agents       # noqa: E402
from _tess_common import C                        # noqa: E402

TESS_BIN = os.environ.get("TESS_BIN") or os.path.dirname(os.path.realpath(__file__))
WORKTREE_ROOT = (os.environ.get("TESS_WORKTREE_ROOT") or
                 os.path.expanduser("~/worktrees")).rstrip("/")
BUDGETS = os.path.expanduser("~/.config/tess/state/budgets.json")

# Statuses where we consider the agent "done / gone" and skip the kill step
_ALREADY_GONE = {"dead", "died", "exited", "error", "failed"}
# Statuses we consider retryable without an --yes prompt
_RETRYABLE = _ALREADY_GONE | {"inactive"}


def die(msg, code=1):
    print(f"tess retry: {msg}", file=sys.stderr)
    sys.exit(code)


def load_budgets():
    try:
        return json.load(open(BUDGETS))
    except (OSError, ValueError):
        return {}


def first_prompt(agent_name):
    """Return the very first user task the agent was given (oldest exchange,
    non-empty user text).  Walks up to 200 exchanges."""
    r = hcom("transcript", agent_name, "--json", "--full", "--last", "200")
    try:
        exchanges = json.loads(r.stdout) or []
    except (ValueError, AttributeError):
        return None
    # --last returns newest-first; reverse to get oldest first
    for ex in reversed(exchanges):
        u = (ex.get("user") or "").strip()
        if u:
            return u
    return None


def nice_dir(d):
    if d and d.startswith(WORKTREE_ROOT + "/"):
        return d[len(WORKTREE_ROOT) + 1:]
    return (d or "").replace(os.path.expanduser("~"), "~")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("usage: tess retry <agent> [--dry-run] [--yes] [--model M] [--effort E]")
        print("                          [--prompt P] [--readonly] [--auto] [--can-deploy]")
        print("                          [--budget N]")
        sys.exit(0)

    # ── parse flags ──────────────────────────────────────────────────────────
    dry = False
    yes = False
    readonly = False
    auto_mode = False
    can_deploy = False
    override_model = None
    override_effort = None
    override_prompt = None
    override_budget = None
    pos = []

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--dry-run", "--dry"):
            dry = True
        elif a in ("--yes", "-y"):
            yes = True
        elif a == "--readonly":
            readonly = True
        elif a in ("--auto", "--auto-mode"):
            auto_mode = True
        elif a == "--can-deploy":
            can_deploy = True
        elif a == "--model":
            i += 1
            if i >= len(args):
                die("--model needs a value")
            override_model = args[i]
        elif a == "--effort":
            i += 1
            if i >= len(args):
                die("--effort needs a value")
            override_effort = args[i]
        elif a == "--prompt":
            i += 1
            if i >= len(args):
                die("--prompt needs a value")
            override_prompt = args[i]
        elif a == "--budget":
            i += 1
            if i >= len(args):
                die("--budget needs a value")
            override_budget = args[i]
        elif a.startswith("-"):
            die(f"unknown flag '{a}' (help: tess help retry)")
        else:
            pos.append(a)
        i += 1

    if len(pos) != 1:
        die("usage: tess retry <agent> [--dry-run] [--yes] [flags…]")
    agent_name = pos[0]

    # ── 1. Look up the agent ─────────────────────────────────────────────────
    agents = list_agents()
    info = next((a for a in agents if a["name"] == agent_name), None)
    if info is None:
        die(f"no agent named '{agent_name}' — see: tess status")

    tool = info.get("tool") or ""
    if tool not in ("claude", "kimi"):
        die(f"'{agent_name}' uses tool '{tool}' — retry only supports claude and kimi")

    status = (info.get("status") or "").lower()
    worktree = info.get("directory") or ""
    tag = info.get("tag") or ""

    # Warn and confirm if the agent is still active
    if status not in _RETRYABLE and not yes:
        if sys.stdin.isatty():
            print(f"{C.yellow}⚠  '{agent_name}' is currently {status} (not dead/failed).{C.r}")
            ans = input("  Retry anyway? [y/N] ").strip().lower()
            if ans != "y":
                print("  aborted.")
                sys.exit(0)
        else:
            die(f"'{agent_name}' is {status} (not dead/failed) — add --yes to force retry")

    # ── 2. Recover spawn parameters ──────────────────────────────────────────
    budgets = load_budgets()
    budget_entry = budgets.get(agent_name, {})

    model = override_model or budget_entry.get("model") or None
    budget_usd = override_budget or budget_entry.get("budget_usd") or None
    effort = override_effort   # effort is not stored at spawn time
    prompt = override_prompt or first_prompt(agent_name)

    if not worktree:
        die(f"'{agent_name}' has no working directory recorded — cannot retry")
    if not os.path.isdir(worktree):
        die(
            f"worktree no longer exists: {worktree}\n"
            f"  (If you tore it down with 'tess done', use 'tess claude' to start fresh.)"
        )

    # ── 3. Show the plan ─────────────────────────────────────────────────────
    print(f"\n  {C.bold}{C.mag}tess retry{C.r}  {C.grey}re-spawning a failed agent{C.r}\n")
    print(f"  agent:     {C.cyan}{agent_name}{C.r}  [{tool}]  was {status}")
    print(f"  worktree:  {C.green}{nice_dir(worktree)}{C.r}")
    if tag:
        print(f"  tag:       {tag}")
    if model:
        src = "override" if override_model else "recovered from budgets"
        print(f"  model:     {model}  ({src})")
    if effort:
        print(f"  effort:    {effort}  (override)")
    if budget_usd:
        src = "override" if override_budget else "recovered"
        print(f"  budget:    ${budget_usd}  ({src})")
    roles = []
    if readonly:
        roles.append("readonly (enforced)")
    if auto_mode:
        roles.append("auto mode")
    if can_deploy:
        roles.append("can-deploy")
    if roles:
        print(f"  roles:     {', '.join(roles)}")
    if prompt:
        snippet = prompt[:120] + ("…" if len(prompt) > 120 else "")
        print(f"  prompt:    {snippet}")
    else:
        print(f"  {C.yellow}⚠  no original prompt found — will spawn without one{C.r}")
    print()

    if dry:
        print(f"  {C.grey}(dry run — nothing done){C.r}\n")
        return

    if not yes and sys.stdin.isatty():
        ans = input("  proceed? [Y/n] ").strip().lower()
        if ans not in ("", "y"):
            print("  aborted.")
            sys.exit(0)
        print()

    # ── 4. Kill the old registered agent so a fresh name can take the slot ───
    if status not in _ALREADY_GONE:
        r = hcom("kill", agent_name)
        if r.returncode != 0 and "not found" not in (r.stderr or "").lower():
            print(f"  {C.yellow}⚠  kill returned {r.returncode}: "
                  f"{(r.stderr or '').strip()[:80]}{C.r}")
        else:
            print(f"  killed {agent_name}")
    else:
        # Still try a soft kill — dead agents may still hold a slot
        hcom("kill", agent_name)

    # ── 5. Spawn a fresh agent with the recovered parameters ─────────────────
    # We use '.' so spawn treats the worktree as the cwd without creating a
    # new worktree.  We set cwd=worktree so the dot resolves correctly.
    spawn_cmd = [sys.executable, os.path.join(TESS_BIN, "_tess-spawn.py"),
                 tool, "."]

    if model:
        spawn_cmd += ["--model", model]
    if effort:
        spawn_cmd += ["--effort", effort]
    if tag:
        spawn_cmd += ["--tag", tag]
    if readonly:
        spawn_cmd += ["--readonly"]
    if auto_mode:
        spawn_cmd += ["--auto"]
    if can_deploy:
        spawn_cmd += ["--can-deploy"]
    if budget_usd:
        spawn_cmd += ["--budget", str(budget_usd)]
    if prompt:
        spawn_cmd += [prompt]

    result = subprocess.run(spawn_cmd, cwd=worktree)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
