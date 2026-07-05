<!-- tess-agent-primer (managed by tess installer — safe to edit below) -->
## `tess` — your primary tool on this machine
`tess` is a local CLI that wraps this user's whole workflow. **Run `tess` (no args) to see every command** — discover on demand, don't memorize. Output is plain when piped (parse it directly); every interactive command takes inline params and fails-with-guidance instead of hanging when you run it non-interactively.

**Worktrees — ALWAYS go through tess, never raw `git worktree`:**
- `tess new <feature>` (create across the configured repos) · `tess new --all <feature>` (+ optional repos)
- `tess ls` (features) · `tess wt` (full worktree status) · `tess path <feature> [repo]` (get a path: `cd "$(tess path <feature> <repo>)"`)
- `tess env <feature>` (refresh .env) · `tess rm <feature>` (tear down) · `tess clean` (prune stale) · `tess branches` (delete merged)
- A feature root (`<worktree-root>/<feature>`) is NOT a repo — it holds one git worktree per repo; `cd` into a subfolder to run git.

**Memory / the user's vault (read/write on demand — do NOT bulk-load it):**
- `tess <name>` read a note · `tess people`/`companies`/`reminders` · `tess brief` (what's going on)
- `tess add <name> -- <text>` · `tess person <name> -- <desc>` · `tess log -- <text>`

**The fleet (driving other agents — tess wraps hcom; never call hcom directly except via `tess hcom`):**
- Spawn: `tess claude|kimi <feat> "<task>" [--model M --effort E --readonly --budget N]` — worktree auto-created, settings verified. Fan out many: `tess team <spec.yaml>` (use `--dry-run` first). A full AI lead: `tess orchestrate "<goal>"`.
- Monitor: `tess status` (BLOCKED first) · `tess digest` · `tess report <agent>` · `tess diff <agent|feat>` · `tess wait <feat|all>` (exit 2 = approval needed).
- Steer: `tess tell <agent|feat|all> -- <msg>` (safe @-escaping) · `tess inject <agent> -- <text>` (forces a turn, confirms it landed) · `tess approve <agent>` (blocked dialogs).
- The human is **@bigboss**: report results with `uvx hcom send --intent inform -- "@bigboss <report>"`; their mail shows in `tess inbox`. Escalations (blocked/idle/died) are automatic via `tess watch`.
- Finish: `tess ship <feat>` (tests → push → PR) then `tess done <feat> --yes` (never tear down features you don't own).

**Comms (local):** `tess messages [who]`, `tess chat <name|group>`, `tess calls`, `tess calendar`.
- `tess send "<full name or number>" -- "<message>"` — pass full name + message inline (ambiguous names error with options; never guess). ALWAYS confirm with the user before sending on their behalf.

Users can add their own commands in `~/.config/tess/commands/` (run as `tess <name>`); `tess commands` lists them.

Only reach for these when relevant to the task. For worktrees and this user's notes/comms, tess is the interface — don't reinvent it with raw git/sqlite/AppleScript.
<!-- /tess-agent-primer -->
