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

**Comms (local):** `tess messages [who]`, `tess chat <name|group>`, `tess calls`, `tess calendar`.
- `tess send "<full name or number>" -- "<message>"` — pass full name + message inline (ambiguous names error with options; never guess). ALWAYS confirm with the user before sending on their behalf.

Users can add their own commands in `~/.config/tess/commands/` (run as `tess <name>`); `tess commands` lists them.

Only reach for these when relevant to the task. For worktrees and this user's notes/comms, tess is the interface — don't reinvent it with raw git/sqlite/AppleScript.
<!-- /tess-agent-primer -->
