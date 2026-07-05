# tess-upgrade — implementation plan

Branch `tess-upgrade` in `/Users/pratham/Wash/tess-upgrade`. Never touch `~/tess` or `main`
(live `~/.local/bin` symlinks point at `~/tess/bin`). One commit per item, each with a shell
acceptance check. Live agents (keto) are off-limits; all agent tests use scratch scaffolding.

## Foundation (F0) — helper resolution
`bin/tess` hardcodes `$HOME/.local/bin/_tess-*.sh`, so a worktree copy would exec the LIVE
helpers. Resolve the script's own real dir (`TESS_BIN`) and prefer siblings, falling back to
`~/.local/bin`. Same for `wt`/`worktree.sh` lookups. Makes every later item testable from this
worktree and is a no-op for the installed copy.
Also add `_hcom()` = `hcom` if on PATH else `uvx hcom` (tess already assumes bare `hcom`).

## Priority 1 — dangerous bugs
- **B1 `--help` footgun**: global intercept in the dispatcher — if any arg position 1 is
  `-h/--help`, exec `_tess-help.sh <cmd>` and exit 0, BEFORE any side effect. Validate
  feature/agent names everywhere one is consumed (`new`, `claude|kimi`, `rm`, `env`, `done`,
  `path`): reject names starting with `-`, reserved words (subcommand names), and path-unsafe
  chars. Fix `wt` + `worktree.sh` too (they're callable directly).
  Accept: `bin/tess claude --help` prints help, exits 0, creates NO worktree dir and calls NO
  hcom (verified with a stub `hcom` on PATH + scratch `TESS_WORKTREE_ROOT`). Same for
  `new/rm/env/kimi`.
- **B4 reliable inject**: new `_tess-inject.sh <agent> [--timeout N] -- <text>` →
  `tess inject`. Loop on `hcom term <agent> --json`: wait `ready==true`, inject text, `--enter`,
  then CONFIRM the turn landed (input box cleared + a new `status:active`/transcript exchange
  after our inject); retry up to N times; exit non-zero on failure with the screen state.
  Accept: spawn a scratch headless haiku agent in a temp dir, inject while busy, prove the
  wrapper waits + lands the turn (transcript shows it), then kill the scratch agent.

## Priority 2 — spawn + worktree lifecycle
- **B2 initial prompt**: `tess claude|kimi [feat] ["prompt"] [--file|-f p]` → pass
  `--hcom-prompt` to hcom. Prompt from arg or file (mutually exclusive; file wins error out).
- **B3 model/effort**: `--model m --effort e` at spawn. claude CLI natively supports
  `--model`/`--effort` (verified) — pass through as tool-args. Alias map: `fable5`→
  `claude-fable-5` etc. kimi: `--model` passes through, `--effort` warns + is dropped.
  Accept (B2+B3): stub hcom captures argv; assert `--hcom-prompt/--model/--effort` arrive; a
  real one-shot spawn smoke test with haiku in scratch dir, then kill.
- **B5 rm/clean/ls truth**: `worktree.sh rm` also removes AGENTS.md + CLAUDE.md symlink then
  the dir (warn + list leftovers if still non-empty — never blind `rm -rf`). `wt prune` also
  sweeps folder shells with no live worktree inside. `wt ls` reports from BOTH folder state and
  `git worktree list` (mark ghosts/missing). Accept: scratch repos + feature lifecycle.
- **B6 `tess done <feat>`**: kill only agents whose `directory` is under that feature's path
  (`hcom list --json`), then `wt rm`, then shell sweep. `--dry-run` shows the kill list.
  Accept: scratch feature + fake agent entries via stub; assert keto never matches.

## Priority 3 — hcom folded in + visibility
- **B7 `tess hcom …`** passthrough + wrappers: `tess kill <agent|feat>`, `tess tell <agent> --
  <msg>` (sends as bigboss). Help wired.
- **B8 `tess report <agent>`** (full last assistant message, plain text, `--n N` for more) and
  **`tess digest`** (all alive agents: name/state/dir/last-report snippet). Built on
  `hcom transcript --json --full` + `hcom list --json` via `_tess-hq.py`.
- **B9 lead identity + inbox**: user is `@bigboss` (external identity via `--from bigboss`).
  `tess inbox` = messages mentioning bigboss (+ broadcasts) since last cursor
  (`~/.config/tess/state/inbox.cursor`); `--all` for full history; marks read.
- **B10 @ escaping**: in `tess tell`/`tess inbox` forwarding paths, message bodies are passed
  via stdin (never argv), and any `@word` that collides with a live agent name gets a
  zero-width space inserted unless it's the intended target — content (emails/handles) renders
  intact, no accidental mentions/DMs.
- **F2 wait + phone notify**: `tess wait <agent|all> [--timeout]` — poll until
  listening/blocked/dead, exit code reflects state. `tess watch [--phone]` — background loop
  (nohup) that iMessages the user (via `_tess-send.sh`, `TESS_NOTIFY_CONTACT` in config) on
  FINISHED / IDLE / BLOCKED transitions. `tess watch off` stops it.
- **F6 escalation to the lead (first-class, user-added)**: any agent that NEEDS INPUT —
  blocked on approval (`■`), asking a question, or idle mid-task — escalates IMMEDIATELY to
  the orchestrating lead, human or AI. Implementation: the `tess watch` loop detects
  active→blocked and active→listening transitions from `hcom list --json` polling (hcom
  `events sub` delivers only to hcom agents, so the watcher ALSO forwards each escalation as
  (a) an hcom message @-mentioning the lead agent when one is registered — the AI-orchestrator
  path, delivered instantly into its conversation — and (b) a `tess inbox` entry for the human
  lead, and (c) optional phone push. Lead identity comes from
  `~/.config/tess/state/lead` (set by `tess orchestrate`, default `bigboss`).
  Acceptance: spawn a scratch agent, force a blocked/idle state, confirm the escalation
  message reaches the lead's inbox (and lead agent's hcom feed) within seconds.
- **F4 monitoring**: `tess status` (rich table: agent, task, state incl. BLOCKED, last
  activity, worktree, unread) + `tess agents --json` (machine). `tess diff <agent|feat>` =
  per-worktree `git diff --stat` of files touched. `tess approve <agent>` = reliable-inject
  Enter to accept the highlighted permission option (uses B4 wrapper; refuses if not blocked).

## Priority 4 — fan-out, orchestrate, ship
- **F1 `tess team <spec.yaml|-> [--dry-run]`**: `_tess-team.py` — spec: defaults
  (tool/model/effort/template) + agents[] (name/feature/prompt/repos/role/readonly). Creates
  worktrees, spawns each with prompt = template + task. Templates from
  `~/.config/tess/templates/*.md` (user) then repo `templates/*.md` (built-in: investigate,
  implement, review). `--dry-run` prints the exact spawn plan, spawns nothing.
- **F3 `tess orchestrate "<goal>"`**: spawns ONE lead agent (hcom, in a scratch/feature dir)
  with `modes/orchestrate.md` appended system prompt: decompose goal → `tess team`/`tess
  claude <feat>` sub-agents → monitor `tess digest`/`tess wait` → synthesize → report
  @bigboss. `--dry-run` prints the lead spawn command.
- **F5 collect→ship→teardown**: `tess ship <feat>` = per-repo diff stat → optional
  `TESS_TEST_CMD_<repo>` → push branch → `gh pr create` (`--merge` opt-in) → prints teardown
  hint. Roles ENFORCED at spawn: `--readonly` → claude `--permission-mode plan`; deploy denied
  by default via `--disallowedTools` on deploy-ish Bash patterns unless `--can-deploy`.
  Budget: `--budget <usd>` → claude `--max-budget-usd` (verified flag exists); `tess spend`
  view = per-agent budget flags recorded in state + surfaced in `tess status`.

## Order of commits
F0 → B1 → B4 → B2+B3 → B5 → B6 → B7 → B8 → B9+B10 → F2 → F4 → F1 → F3 → F5 → docs/help/README
sweep + final `hcom send` summary.

## Test scaffolding (never touches real repos/agents)
`/tmp` scratch: fake `TESS_CORE` with 2 tiny git repos, scratch `TESS_WORKTREE_ROOT`, stub
`hcom` script on PATH that logs argv to a file (for no-spawn assertions), real hcom only for
scratch headless haiku agents (killed right after).
