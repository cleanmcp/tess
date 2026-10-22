# Worktrees

[← README](../README.md)

Sessions ride on git worktrees. You can also drive them directly for multi-repo feature work.

## Create

```bash
tess new <feature>              pick a repo (interactive) or the repo you're in
tess new <repo> <feature>       any repo on disk, by name
tess new <feature> --repo a,b   an explicit set
tess new <feature> --fleet      your configured TESS_REPOS (opt-in — set in ~/.config/tess/config)
tess new <feature> --all        TESS_REPOS_ALL if configured (same config file — not hardcoded)
tess new <feature> --base dev   cut from a branch other than main
```

The grammar is deterministic. An **unknown repo is an error**, never silently reinterpreted. When several repos share a name, tess picks the one you actually work in (zoxide frecency + git activity); a genuine tie shows a picker.

Feature names: letters, digits, `.` `_` `-`. Not a flag, not a path, not a reserved tess word.

## Work in one

```bash
cd "$(tess path <feature>)"          single-repo → lands INSIDE the repo
cd "$(tess path <feature> <repo>)"   multi-repo  → that repo's worktree
```

A **multi-repo** feature root is not a git repo — it holds one worktree per repo side by side, with an `AGENTS.md` explaining the layout. Run git inside a subfolder.

A **single-repo** feature has no folder shell, so `tess path` output is always safe to `cd` into.

## Inspect & tear down

```bash
tess ls          feature names
tess wt          status: every feature → repos, branch, dirty count, source repo
tess repos       the repo map — every repo on disk, ranked by use
tess env <feat>  re-copy .env files (git worktrees don't carry untracked files)
tess rm <feat>   remove the worktrees (branches survive)
tess clean       prune stale registrations
tess branches    list branches already merged to main, offer to delete
```

## Raw `git worktree` is blocked

If you wired your agents (`tess wire`), a hook denies `git worktree add/remove/move` and hands back the `tess new` equivalent — because raw git skips the `.env` copy, the registration that makes `tess wt` / `ship` / `done` see it, and the orientation file.

One-off escape hatch:

```bash
TESS_ALLOW_RAW_GIT=1 git worktree add ../wherever
```

`git worktree list` is read-only and always allowed.

## Todos

A plain-markdown checklist that outlives the session. Open items are injected into every new agent session via a `SessionStart` hook.

```bash
tess todo                          list open
tess todo add [-p <proj>] <text>   add (auto-tagged with the current repo)
tess todo done <id>
```

## Cut one on another machine

```bash
tess new --on mini <feature>                 the repo you're standing in
tess new --on mini Mono-icarus <feature>     that repo by name
tess new --on mini <feature> --base dev
tess new --on mini <feature> --no-setup      skip the dependency install
tess new --on mini <feature> --dry-run
```

Same grammar as local `tess new`, one flag added. The peer does the work — its own
`tess new` runs there, so the worktree lands in **its** configured root, by its rules, with
**its** `.env` files copied in. Then dependencies are installed there, because a worktree you
cannot run isn't finished. If its tess refuses (unknown repo, unsafe feature name), you see
that machine's own wording.

Feature names are flat — letters, digits, `.` `_` `-`. A branch-style name like `fix/thing`
is not a feature name; the branch is named after the feature.

Peers come from the same setting the other cross-machine commands read:

```bash
TESS_PEERS="mini=mac-mini  box=dev@10.0.0.5"     # ~/.config/tess/config
```

Related: `tess handoff <peer>` moves a session that is *already running* here, and
`tess tunnel <peer> <port>` opens that machine's dev server on this one.
