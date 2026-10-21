---
name: tess-worktrees
description: Use tess to create and manage isolated git worktrees for feature work. Trigger whenever work should be isolated from the current checkout, when starting a feature/fix/experiment that shouldn't touch the working tree, when running two or more changes in parallel, or when the user says "worktree", "isolate this", "new branch for", "work on this separately", "spin up", "in parallel", "don't touch main". ALSO trigger before running any raw `git worktree` command — tess owns worktree creation and a PreToolUse hook will block the raw call.
---

# Worktrees, via tess

`tess new` is how a worktree gets created here. Raw `git worktree add` is blocked by a hook —
it skips `.env` copying, the repo map, the agent orientation file, and the teardown path.

**Check it exists first.** `command -v tess` — if missing, tell the user tess isn't installed
(`https://github.com/cleanmcp/tess`) and fall back to normal git. Don't fight the hook.

## Creating

The grammar is deterministic. An unknown repo name is an error, never a guess.

```bash
tess new <feature>                 # outside any repo → pick from indexed repos (fzf);
                                   # inside a repo → that repo only; --fleet for TESS_REPOS
tess new <repo> <feature>          # any repo on disk by name (tess maps them — see `tess repos`)
tess new <feature> --repo a,b      # explicit repo list
tess new <feature> --fleet         # the configured default set
tess new <feature> --all           # the set incl. optional repos
tess new <feature> --base <branch> # cut from something other than main
```

Feature names: letters, digits, `.` `_` `-`. No slashes, no leading dash, and not a reserved
tess word (`status`, `ship`, `new`, `todo`, …) — tess rejects those with a clear error.

## Working in one

```bash
cd "$(tess path <feature>)"           # single-repo feature → lands INSIDE the repo
cd "$(tess path <feature> <repo>)"    # multi-repo feature → that repo's worktree
```

A **multi-repo** feature root is *not* a git repo — it holds one worktree per repo side by side,
with an `AGENTS.md` at the root explaining the layout. `git` commands must run inside a subfolder.
A **single-repo** feature returns the repo dir itself, so `tess path` output is always safe to `cd` into.

## Inspecting and tearing down

```bash
tess ls                 # feature names
tess wt                 # status table: every feature → its repos, branch, dirty count, source repo
tess repos              # the repo map — every repo on disk, ranked by how much it's used
tess env <feature>      # re-copy .env files in (git worktrees don't carry untracked files)
tess rm <feature>       # tear down the worktrees (branches survive)
tess clean              # prune stale registrations after folders were deleted by hand
tess branches           # list branches already merged to main, offer to delete
```

If a worktree is missing its env vars, the answer is `tess env <feature>` — not hand-copying files.

## When to reach for this

Reach for a worktree when the change is big enough that you'd rather not have it half-applied in
the user's checkout, when two changes must proceed at once, or when spawning an agent to do the
work (see the `tess-fleet` skill — spawning creates the worktree for you).

Do **not** create a worktree for a one-line edit in the repo the user is already sitting in.

## Persistent todos

The checklist survives the session. Open items are injected into every new agent session by a
`SessionStart` hook, so the next session picks up where this one stopped.

```bash
tess todo                          # list open
tess todo add [-p <project>] <text>
tess todo start <id>               # mark in progress ([/] — survives the session)
tess todo done <id>
tess todo board                    # the same list as a kanban board
```

Check items off when you finish them; mark the one you're on with `start`; add follow-up
work you uncover. Prefer this over an in-session-only list. Don't recite the whole list
back to the user unless asked. (These are coding todos — tasks inside the user's NOTES are
`tess tasks`, see the tess-vault skill.)

## Notes

- Output is colored for a human and plain when piped — parse it directly.
- Every command takes inline params and fails with guidance rather than hanging when
  run non-interactively. `--help` on any subcommand is always safe: it never creates or spawns.
- Users can add their own commands in `~/.config/tess/commands/`; `tess commands` lists them.
- `tess` with no args prints the full menu. `tess help <cmd>` details one command. When unsure
  of a flag, run the help — don't guess.
