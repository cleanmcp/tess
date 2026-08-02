# Changelog

All notable changes to tess are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **The vault layer — tess as a knowledge-base provider for agents.** `tess vault` (the
  orientation map + `folders`/`mkdir`/`init <dir>` workspace scaffolding), `tess note`
  (new/ls/path/show — proper frontmatter, templates with `{{vars}}`), `tess kanban` (full
  board CRUD on Lokus-native `.kanban` files: app-schema-exact, atomic, clobber-safe),
  `tess tasks` (every checkbox state across notes + `tasks done <match>`), `tess base`
  (database-style queries over frontmatter + saved `.base` views), `tess links`
  (backlinks/outlinks/`--broken`), `tess canvas` (Excalidraw). Everything degrades to a
  plain markdown folder — Lokus extras light up when present. Docs: `docs/vault.md`.
- **`tess todo start <id>` + `tess todo board`** — an in-progress state (`[/]`) and a
  kanban view for the cross-session coding checklist.
- **New `tess-vault` skill** teaching agents the whole layer (where to write, the
  todo-vs-tasks-vs-kanban distinction, the exit-3 ambiguity contract). Existing installs:
  re-run `tess wire` once to pick it up.

### Changed
- `tess reminders` now shows every open checkbox state (`[ ]` `[/]` `[!]` `[?]` `[>]`),
  not just `- [ ]`.
- Reserved-word safety: managing an EXISTING feature (`rm`/`path`/`env`/`done`/`ship`)
  no longer rejects names that later became reserved words — only creation does.

## [0.1.0] — 2026-07-27

First tagged release. tess had been an internal tool; this is the pass that makes it safe to hand to someone else's laptop.

### Added
- **Agent wiring — `tess wire`.** Teaches every AI coding agent on the machine about tess, in three layers: portable `SKILL.md` skills (Claude Code · Cursor · Codex · Gemini · opencode), a shell guard that blocks raw `git worktree` and redirects to `tess new` (Claude Code + Cursor), and the `agent-primer.md` block for agents with neither. Idempotent, symlink-based, `--dry-run` and `--undo`.
- **Claude Code plugin** (`.claude-plugin/`) — `/plugin marketplace add cleanmcp/tess` installs the skills, the guardrail, and the `/tess:status|new|ship|fleet|todo` commands as a versioned unit.
- `tess --version` (also `version`, `-V`) — version plus the commit it's running.
- `uninstall.sh` — removes what `install.sh` added. Never touches repos, worktrees, or your vault.
- `TESS_NO_AUTOUPDATE=1` — opt out of the background self-update. `tess update` still works.

### Fixed
- **`tess claude|kimi` no longer leaves orphans.** It checked for the agent CLI and the fleet backend *after* creating the worktree and branch, so a machine without them ended up with stray worktrees the user had to clean up by hand. Dependencies are now verified before anything touches disk, and a failed launch rolls the worktree back.
- **`config.example` no longer ships fictional repos.** `TESS_REPOS="app api"` was uncommented, so a new user's first `tess new <feature>` failed complaining about repos they'd never heard of. The fleet is now opt-in and commented, and the no-repos path gives real guidance.
- **Unknown flags no longer search your notes.** `tess --version` (and any unrecognised `-flag`) fell through the dispatcher's catch-all into the vault lookup and printed private note filenames. Unknown options now error with exit 2.
- **`tess status` / `tess digest` no longer claim "no agents running" when the fleet backend is missing** — an empty result and an uninstalled backend were indistinguishable. They now name the actual problem, matching `tess agents`.
- `tess ls` no longer leaks a raw `find: … No such file or directory` on a machine with no worktrees yet, and says "no features yet" instead of printing an empty header.
- `tess new`'s flag errors pointed at the internal `libexec/worktrees/worktree.sh --help` path; they now point at `tess help new`.

### Changed
- README states the platform story honestly: core is portable, and the macOS-only commands are named. Menu entries for the macOS-only sections are marked.

[Unreleased]: https://github.com/cleanmcp/tess/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/cleanmcp/tess/releases/tag/v0.1.0
