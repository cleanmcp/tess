# tess — multi-agent orchestration upgrade

## Mission
Make `tess` the user's single tool for driving many AI coding agents at once ("tell one AI to work on many things"): worktrees + agent spawning + coordination, with the separate **hcom** CLI folded IN. Fix the friction below and add the features. You are running on **Fable 5 / xhigh** — think hard, be surgical.

## Where to work (READ THIS)
- Work ONLY in this worktree: `/Users/pratham/Wash/tess-upgrade` (branch `tess-upgrade`).
- The real repo is `~/tess`; its `bin/` is **symlinked into `~/.local/bin` (the user's live PATH)** — so editing `~/tess/bin/*` would change the user's live tess mid-edit. NEVER edit `~/tess` directly. NEVER touch `main`.
- Commit incrementally to `tess-upgrade`. Each change must be independently testable and must NOT break existing `tess`/worktree/hcom behavior.
- Other AI agents are live in this session (e.g. `keto`). **Do NOT kill or message other agents.** Don't run destructive hcom/tess commands against anything but your own test scaffolding.
- Plan first (write PLAN.md), implement in priority order, test each item, report progress via `hcom send`.

## Codebase map (grounding)
- `bin/tess` (~439 lines) — main bash dispatcher (`case` on subcommand). The `claude|kimi)` agent-spawn path is ~L289-305 (creates worktree if named, opens cmux, hands to hcom). Add new subcommands here + dispatch to helpers.
- `bin/worktree.sh` (~167) — `new`/`rm`/`clean`/`ls`/`env`. Bug: `rm` removes git worktrees but leaves the feature folder shell (AGENTS.md/CLAUDE.md symlink); `clean` doesn't remove those; `ls` reads folders not real worktree state.
- `bin/_tess-help.sh` — help text (per-subcommand). Wire new help here.
- `bin/_tess-*.sh` / `bin/_tess-*.py` + `bin/_tess_common.py` — helper convention; symlinked into `~/.local/bin` (see `_tess-update.sh`). Follow this pattern for new subcommands.
- `bin/_tess-send.sh` — sends iMessages; **reuse for phone-notify**.
- `hcom` is an EXTERNAL CLI (`hcom [N] claude|kimi [flags] [tool-args]`, `send`, `list`, `events`, `transcript`, `term inject`, `kill`, `bundle`, `r`/`f`). tess should WRAP it, not reinvent it.
- Config/state: `~/.config/tess`.

## BUGS / FRICTION (fix these)
- **B1 (do first — dangerous):** `tess <sub> --help`/`-h` is treated as a FEATURE NAME. `tess claude --help` literally created a junk worktree AND spawned a stray agent. A help flag must NEVER create/spawn. Add real `--help`/`-h` to every subcommand and reject flag-like/reserved names as feature names.
- **B4 (do early):** `hcom term inject … --enter` reports success but SILENTLY drops when the agent is busy (screen `ready=false`) — no turn registers. Build a reliable inject wrapper: wait-until-ready, submit, then CONFIRM the turn actually landed (via `hcom term` screen state / transcript), retry if not.
- **B2:** No initial prompt at spawn. Add `tess claude|kimi <feat> "<prompt>"` (+ `--file/-f`).
- **B3:** No model/effort at spawn. Add `--model` and `--effort` applied at launch (e.g. `--model fable5 --effort xhigh`).
- **B5:** `tess rm` leaves folder shells; `tess clean` doesn't remove them; `tess ls` shows ghost features. Make rm/clean fully remove + ls reflect real worktree state.
- **B6:** Add one-shot `tess done <feat>` = kill its agents + close cmux panes + rm worktree + clean folder.
- **B7:** Fold hcom UNDER tess so the user only touches tess.
- **B8:** Reading output is clunky (transcript truncates; events is raw JSON). Add scriptable `tess report <agent>` (full last message) + `tess digest` (merged summary of all agents).
- **B9:** No orchestrator inbox — the lead shows "not participating"; agents inconsistently DM `@bigboss`. Give the lead a first-class identity + `tess inbox`.
- **B10:** hcom parses `@` as mentions, mangling report content (emails/handles). Handle/escape it.

## FEATURES (priority order)
- **F1 — one-command fan-out (killer):** `tess team <spec.yaml|heredoc>` — spawn N agents across worktrees in one shot, each with its own prompt + model + effort + role; reusable task **templates** (e.g. `--template investigate` injects "read-only, report via hcom, don't implement"); `--dry-run`.
- **F2 — lead + inbox + phone-notify (user is away for hours):** make the user `@bigboss` with `tess inbox` (unread agent reports); push to their phone via `_tess-send.sh` when an agent FINISHES / goes IDLE / is BLOCKED on approval; `tess wait <agent|all>`.
- **F3 — orchestrator mode:** `tess orchestrate "<goal>"` — a lead AI decomposes the goal, spawns sub-agents, monitors, synthesizes their reports.
- **F4 — monitoring:** `tess status` / `tess agents --json` (per agent: task, state, last activity, worktree, tokens); surface BLOCKED-on-approval + `tess approve <agent>`; per-agent live diff (files touched).
- **F6 — notification/escalation (FIRST-CLASS, user-added):** when ANY hcom agent NEEDS INPUT — blocked on a permission/approval prompt, asking a question, or idle mid-task — the ORCHESTRATING lead (human OR `tess orchestrate` AI) must be notified IMMEDIATELY so no stuck sub-agent is missed. Design: tess subscribes to hcom idle/blocked/needs-input events (`hcom events sub --idle/--blocked`, `■` status) and routes them to the lead's inbox (`tess inbox`) AND optionally the user's phone via `_tess-send.sh`. Works for both a human lead and an AI orchestrator. Acceptance: spawn a test agent, make it block, confirm the lead gets pinged.
- **F5 — collect → ship → teardown:** `tess digest`; `tess ship <feat>` (diff → tests → PR/merge → deploy); `tess done <feat>`; ENFORCED `--readonly`/`--can-deploy` roles (not just prompt text); budget caps (`--budget`, total spend view, auto-stop at cap).

## Don't regress (already good)
`tess new` (fast, both repos, auto-copies .env), spawn→cmux→hcom coordination, `hcom kill` closing panes, `hcom term`/inject/transcript primitives.

## Definition of done
Each item implemented, wired into help, symlinked if a new helper, and proven with a shell acceptance check (esp. B1: prove `tess claude --help` prints help and does NOT create a worktree/agent). Commit per item. Post a final summary via `hcom send`.
