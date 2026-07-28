#!/usr/bin/env bash
# tess SessionStart hook — a one-line pointer + the open coding todos.
#
# Deliberately tiny. The detail lives in the `tess:worktrees` and `tess:fleet` skills, which
# load only when the task actually calls for them. This runs every session, so it stays cheap.
# Silent and exit-0 in every failure path: a broken hook must never block a session.
set -uo pipefail

command -v tess >/dev/null 2>&1 || exit 0

echo "tess is installed here — it owns git worktrees (\`tess new\`, not \`git worktree add\`),"
echo "parallel agent sessions, and the persistent todo list. Run \`tess\` to see every command."

# open todos (plain, compact, silent when empty — never errors)
tess todo --hook 2>/dev/null || true

exit 0
