---
description: Create an isolated tess worktree for a feature and start working in it
argument-hint: <feature> [what to build]
allowed-tools: Bash(tess:*), Read, Grep, Glob
---

Create an isolated worktree for: **$ARGUMENTS**

Existing features (don't collide with these):

!`tess ls 2>&1 | head -20`

Steps:

1. Pick a short kebab-case feature name from my request if I didn't give one explicitly.
   Letters/digits/`.`/`_`/`-` only, and not a reserved tess word.
2. Run `tess new <feature>` — from inside a repo it uses that repo; outside one it uses my
   configured set. Add `--repo a,b` / `--all` / `--base <branch>` only if my request implies it.
3. `cd "$(tess path <feature>)"` and confirm where you landed.
4. If the repo needs env vars, run `tess env <feature>`.
5. Then start on the actual work described above. If there's no work described, just report the
   path and stop.

Don't create the worktree if a feature by that name already exists — tell me and ask.
