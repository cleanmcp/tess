<!-- tess-agent-primer (managed by tess installer — safe to edit below) -->
## `tess` — session orchestration, your primary tool here
`tess` is a local CLI for running many AI coding **sessions** at once — each an isolated worktree + agent + context you spawn, watch, steer, and ship. **Run `tess` (no args) to see every command** — discover on demand, don't memorize. Output is plain when piped (parse it directly); every interactive command takes inline params and fails-with-guidance instead of hanging when you run it non-interactively.

**Worktrees — ALWAYS go through tess, never raw `git worktree`. The grammar is deterministic:**
- `tess new <feature>` — the repo you're standing in (a fleet repo, or outside any repo → the configured set) · `tess new <repo> <feature>` — that repo by name (an unknown repo is an ERROR, never reinterpreted) · flags: `--repo a,b` · `--fleet`/`--all` · `--base <branch>`
- `tess ls` (features) · `tess wt` (worktree status: repos, branch, dirty) · `tess path <feature> [repo]` (get a path: `cd "$(tess path <feature> <repo>)"` — a single-repo feature returns the repo dir itself, so you always land inside a git repo)
- `tess env <feature>` (refresh .env) · `tess rm <feature>` (tear down) · `tess clean` (prune stale) · `tess branches` (delete merged)
- A MULTI-repo feature root (`<worktree-root>/<feature>`) is NOT a repo — it holds one git worktree per repo; `cd` into a subfolder to run git (its AGENTS.md explains the layout).

**Coding todos (persistent across sessions — the open ones are shown to you at session start):**
- `tess todo` (list open) · `tess todo add [-p <project>] <text>` · `tess todo done <id>` (check off) · `tess todo all` · `tess todo rm <id>`.
- This is the shared work-tracker across sessions. When you finish a listed item, check it off; when you uncover follow-up work, add it. Prefer it over an in-session-only todo so the next session (and the human) sees the real state. Don't restate the whole list back to the user unless asked.

**Memory / the user's vault (OPTIONAL — only if a vault is configured; read/write on demand, never bulk-load it):**
- `tess <name>` read a note · `tess people`/`companies`/`reminders` · `tess brief` (what's going on)
- `tess add <name> -- <text>` · `tess person <name> -- <desc>` · `tess log -- <text>`

**The fleet (driving other agents — tess wraps hcom; never call hcom directly except via `tess hcom`):**
- Spawn: `tess claude|kimi <feat> "<task>" [--model M --effort E --readonly --budget N]` — worktree auto-created, settings verified. Fan out many: `tess team <spec.yaml>` (use `--dry-run` first). A full AI lead: `tess orchestrate "<goal>"`.
- Monitor: `tess status` (BLOCKED first) · `tess digest` · `tess report <agent>` · `tess diff <agent|feat>` · `tess wait <feat|all>` (exit 2 = approval needed).
- Steer: `tess tell <agent|feat|all> -- <msg>` (safe @-escaping) · `tess inject <agent> -- <text>` (forces a turn, confirms it landed) · `tess approve <agent>` (blocked dialogs).
- The human is **@bigboss**: report results with `uvx hcom send --intent inform -- "@bigboss <report>"`; their mail shows in `tess inbox`. Escalations (blocked/idle/died) are automatic via `tess watch`.
- Finish: `tess ship <feat>` (tests → push → PR) then `tess done <feat> --yes` (never tear down features you don't own).

**Comms (OPTIONAL — macOS + Full Disk Access; local):** `tess messages [who]`, `tess chat <name|group>`, `tess calls`, `tess calendar`.
- `tess send "<full name or number>" -- "<message>"` — pass full name + message inline (ambiguous names error with options; never guess). ALWAYS confirm with the user before sending on their behalf.

Users can add their own commands in `~/.config/tess/commands/` (run as `tess <name>`); `tess commands` lists them.

Only reach for these when relevant to the task. For worktrees and this user's notes/comms, tess is the interface — don't reinvent it with raw git/sqlite/AppleScript.
<!-- /tess-agent-primer -->
