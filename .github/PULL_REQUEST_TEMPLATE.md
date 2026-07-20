## What

<!-- one tight paragraph: what changes, and the user-visible effect -->

## Why

<!-- the problem this solves; link the issue if there is one -->

## Verified

<!-- prove it — paste real output, not "should work" -->

- [ ] `tests/smoke.sh` passes (syntax + the worktree battery, all in a temp dir)
- [ ] ran the touched command(s) for real; output above

## Conventions (see CONTRIBUTING.md)

- [ ] nothing user-specific in code, defaults, or examples — machine-specific values go through `TESS_*` config
- [ ] `--help` stays safe: never creates a worktree, spawns an agent, or mutates state
- [ ] non-interactive callers (agents/pipes) get inline params + fail-with-guidance, never a hang
- [ ] positional args stay deterministic — ambiguity is an error or a picker, never a guess
