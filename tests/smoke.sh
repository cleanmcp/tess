#!/usr/bin/env bash
# tess smoke tests — syntax + the worktree battery + dispatcher basics.
# Safe to run anywhere: every worktree/todo/state path is overridden into a temp
# dir (env beats ~/.config/tess/config), nothing touches your real setup.
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TESS="$ROOT_DIR/bin/tess"
WT="$ROOT_DIR/libexec/worktrees/worktree.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

export TESS_WORKTREE_ROOT="$TMP/wtroot" TESS_CORE="$TMP/core" \
       TESS_REPOS="repo-a repo-b" TESS_REPOS_ALL="repo-a repo-b" \
       TESS_MAIN_BRANCH=main TESS_GIT_REMOTE="" TESS_STATE="$TMP/state"

pass=0; fail=0
ok()  { pass=$((pass+1)); echo "  ✓ $1"; }
bad() { fail=$((fail+1)); echo "  ✗ $1"; }
t()   { local d="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$d"; else bad "$d"; fi; }
t_not(){ local d="$1"; shift; if "$@" >/dev/null 2>&1; then bad "$d"; else ok "$d"; fi; }

mkrepo() {
  git init -q -b main "$1"
  ( cd "$1" && echo hi > f.txt && echo "SECRET=1" > .env \
    && git add f.txt && git -c user.email=t@t -c user.name=t commit -qm init )
}

echo "== syntax =="
sh_fail=0
for f in "$ROOT_DIR"/bin/tess "$ROOT_DIR"/install.sh "$ROOT_DIR"/libexec/*/*.sh \
         "$ROOT_DIR"/libexec/worktrees/wt "$ROOT_DIR"/tests/smoke.sh; do
  bash -n "$f" || { echo "    syntax: $f"; sh_fail=1; }
done
[ "$sh_fail" = 0 ] && ok "bash -n every shell script" || bad "bash -n every shell script"
py_fail=0
for f in "$ROOT_DIR"/libexec/*/*.py; do
  python3 -m py_compile "$f" 2>/dev/null || { echo "    py: $f"; py_fail=1; }
done
[ "$py_fail" = 0 ] && ok "py_compile every python helper" || bad "py_compile every python helper"

echo "== worktrees: fleet fan-out =="
mkrepo "$TMP/core/repo-a"; mkrepo "$TMP/core/repo-b"; mkrepo "$TMP/repo-c"
( cd "$TMP" && bash "$WT" feat1 ) >/dev/null 2>&1
t "creates a worktree per fleet repo"      test -e "$TMP/wtroot/feat1/repo-a/.git" -a -e "$TMP/wtroot/feat1/repo-b/.git"
t "copies .env files in"                   grep -q SECRET "$TMP/wtroot/feat1/repo-a/.env"
t "multi-repo feature gets AGENTS.md"      test -f "$TMP/wtroot/feat1/AGENTS.md"
t "path <feat> = feature root (multi)"     test "$("$TESS" path feat1)" = "$TMP/wtroot/feat1"
t "path <feat> <repo> = the repo dir"      test "$("$TESS" path feat1 repo-a)" = "$TMP/wtroot/feat1/repo-a"

echo "== worktrees: single repo =="
( cd "$TMP/repo-c" && bash "$WT" featsolo ) >/dev/null 2>&1
t "cwd repo outside the fleet -> that repo"  test -e "$TMP/wtroot/featsolo/repo-c/.git"
t_not "single-repo feature gets NO AGENTS.md" test -f "$TMP/wtroot/featsolo/AGENTS.md"
t "path lands INSIDE the single repo"        test "$("$TESS" path featsolo)" = "$TMP/wtroot/featsolo/repo-c"

echo "== worktrees: deterministic grammar =="
t_not "unknown repo errors (never reinterpreted)" bash "$WT" definitely-not-a-repo-zz featx
t_not "...and creates no ghost dirs"              test -e "$TMP/wtroot/definitely-not-a-repo-zz" -o -e "$TMP/wtroot/featx"
t_not "three positionals error"                   bash "$WT" a b c
git -C "$TMP/core/repo-a" branch dev
( cd "$TMP" && bash "$WT" --repo "$TMP/core/repo-a" featdev --base dev ) >/dev/null 2>&1
t "--base cuts from the given branch"  test "$(git -C "$TMP/wtroot/featdev/repo-a" rev-parse --abbrev-ref HEAD)" = featdev

echo "== dispatcher =="
echo "NEW=2" >> "$TMP/repo-c/.env"
"$TESS" env featsolo >/dev/null 2>&1
t "env refresh follows gitdir pointer (non-fleet repo)" grep -q NEW "$TMP/wtroot/featsolo/repo-c/.env"
t "tess wt runs"            "$TESS" wt
t "tess ls runs"            "$TESS" ls
t "tess help new exits 0"   "$TESS" help new
before="$(ls "$TMP/wtroot" | wc -l)"
t "tess claude --help is safe"  "$TESS" claude --help
t "...created nothing"          test "$(ls "$TMP/wtroot" | wc -l)" = "$before"
t "spawn --dry-run exits 0"     "$TESS" claude feat1 "smoke" --dry-run
t "resume --plain lists non-tty" "$TESS" resume --plain

echo "== todos (TESS_STATE override) =="
"$TESS" todo add -p smoke "temp item" >/dev/null 2>&1
id="$(sed -nE 's/^- \[ \] \(([0-9a-f]{3})\) temp item.*/\1/p' "$TMP/state/todos.md" | head -1)"
t "todo add lands in the overridden state file" test -n "$id"
"$TESS" todo done "$id" >/dev/null 2>&1
t "todo done checks it off"  grep -q "^- \[x\] ($id)" "$TMP/state/todos.md"
"$TESS" todo rm "$id" >/dev/null 2>&1
t_not "todo rm removes it"   grep -q "($id)" "$TMP/state/todos.md"

echo "== agent wiring (skills · plugin · guard hook) =="
GUARD="$ROOT_DIR/hooks/guard.py"
# the guard must be able to find `tess` for any of this to fire
export PATH="$ROOT_DIR/bin:$PATH"
_g() { echo "$2" | python3 "$GUARD" 2>/dev/null; }
_denies() { _g x "$1" | grep -q '"deny"'; }
_allows() { [ -z "$(_g x "$1")" ]; }

t "plugin.json is valid json"      python3 -c "import json;json.load(open('$ROOT_DIR/.claude-plugin/plugin.json'))"
t "marketplace.json is valid json" python3 -c "import json;json.load(open('$ROOT_DIR/.claude-plugin/marketplace.json'))"
t "hooks.json is valid json"       python3 -c "import json;json.load(open('$ROOT_DIR/hooks/hooks.json'))"
t "cursor-hooks.json is valid json" python3 -c "import json;json.load(open('$ROOT_DIR/hooks/cursor-hooks.json'))"
# every skill needs frontmatter whose name matches its directory (hosts key off both)
sk_fail=0
for d in "$ROOT_DIR"/skills/*/; do
  n="$(basename "$d")"
  [ -f "$d/SKILL.md" ] || { echo "    no SKILL.md: $n"; sk_fail=1; continue; }
  grep -q "^name: $n\$"   "$d/SKILL.md" || { echo "    name != dir: $n"; sk_fail=1; }
  grep -q "^description: " "$d/SKILL.md" || { echo "    no description: $n"; sk_fail=1; }
done
[ "$sk_fail" = 0 ] && ok "every skill has matching name + description" || bad "every skill has matching name + description"

t "guard denies git worktree add"    _denies '{"tool_name":"Bash","tool_input":{"command":"git worktree add ../f b"}}'
t "guard denies it after cd &&"      _denies '{"tool_name":"Bash","tool_input":{"command":"cd /r && git worktree add ../f b"}}'
t "guard denies git -C … worktree add" _denies '{"tool_name":"Bash","tool_input":{"command":"git -C /r worktree add ../f b"}}'
t "guard denies worktree remove"     _denies '{"tool_name":"Bash","tool_input":{"command":"git worktree remove ../f"}}'
t "guard allows worktree list"       _allows '{"tool_name":"Bash","tool_input":{"command":"git worktree list"}}'
t "guard allows the string in echo"  _allows '{"tool_name":"Bash","tool_input":{"command":"echo git worktree add"}}'
t "guard allows the string in rg"    _allows '{"tool_name":"Bash","tool_input":{"command":"rg \"git worktree add\" ."}}'
t "guard honours the inline bypass"  _allows '{"tool_name":"Bash","tool_input":{"command":"TESS_ALLOW_RAW_GIT=1 git worktree add ../f b"}}'
t "guard ignores non-Bash tools"     _allows '{"tool_name":"Read","tool_input":{"file_path":"x"}}'
t "guard fails open on junk input"   _allows 'not json at all'
t "guard speaks Cursor's schema"     bash -c "echo '{\"hook_event_name\":\"beforeShellExecution\",\"command\":\"git worktree add ../f b\"}' | python3 '$GUARD' | grep -q '\"permission\": \"deny\"'"
t "guard never GRANTS permission"    bash -c "! echo '{\"hook_event_name\":\"beforeShellExecution\",\"command\":\"rm -rf /tmp/x\"}' | python3 '$GUARD' | grep -q 'allow'"
t "guard fails open without tess"    bash -c "[ -z \"\$(echo '{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git worktree add a b\"}}' | env PATH=/nonexistent python3 '$GUARD')\" ]"
t "tess wire --dry-run changes nothing" bash -c "HOME='$TMP/fakehome' '$TESS' wire --dry-run >/dev/null && [ ! -d '$TMP/fakehome/.agents' ]"
t "tess help wire exits 0"          "$TESS" help wire

echo "== first-run / OSS hygiene regressions =="
FAKE="$TMP/fresh"; mkdir -p "$FAKE/home" "$FAKE/bin" "$FAKE/elsewhere"
ln -sf "$(command -v git)" "$FAKE/bin/git" 2>/dev/null
ln -sf "$(command -v python3)" "$FAKE/bin/python3" 2>/dev/null
# a machine with git+python but NO agent CLI and NO fleet backend
_fresh() { env -i HOME="$FAKE/home" PATH="$FAKE/bin:/usr/bin:/bin" TERM=dumb bash "$TESS" "$@" 2>&1; }

t "tess --version reports a version" bash -c "'$TESS' --version | grep -qE '^tess [0-9]+\.[0-9]+'"
t "VERSION file exists"              test -f "$ROOT_DIR/VERSION"
t "CHANGELOG exists"                 test -f "$ROOT_DIR/CHANGELOG.md"
t "uninstall.sh exists + parses"     bash -n "$ROOT_DIR/uninstall.sh"
# an unknown flag must ERROR, never fall through to the vault note search
t_not "unknown flag exits nonzero"   "$TESS" --definitely-not-a-command
t "unknown flag says 'unknown option'" bash -c "'$TESS' --nope 2>&1 | grep -q 'unknown option'"
# config.example must not ship placeholder repos as live settings
t_not "config.example has no live TESS_REPOS" grep -qE '^TESS_REPOS=' "$ROOT_DIR/config.example"
t "config.example documents the autoupdate opt-out" grep -q 'TESS_NO_AUTOUPDATE' "$ROOT_DIR/config.example"
# spawn must refuse BEFORE creating anything when its deps are absent
t "spawn preflights missing deps"    bash -c "! _o=\$(env -i HOME='$FAKE/home' PATH='$FAKE/bin:/usr/bin:/bin' bash '$TESS' claude probefeat 'x' 2>&1); echo \"\$_o\" | grep -q \"isn't on your PATH\""
t "...and created NO worktree"       test ! -d "$FAKE/home/worktrees/probefeat"
t "...and left no stray branch"      bash -c "! git -C '$ROOT_DIR' branch --list probefeat | grep -q ."
# a fresh machine must not leak raw find/stderr noise
t_not "tess ls leaks no find/stderr noise on a fresh machine" \
  bash -c "env -i HOME='$FAKE/home' PATH='$FAKE/bin:/usr/bin:/bin' bash '$TESS' ls 2>&1 | grep -qE 'No such file or directory|^find:'"
t "fleet cmds name a missing backend" bash -c "env -i HOME='$FAKE/home' PATH='$FAKE/bin:/usr/bin:/bin' bash '$TESS' status 2>&1 | grep -q 'backend'"

echo "== teardown =="
bash "$WT" rm feat1    >/dev/null 2>&1
bash "$WT" rm featsolo >/dev/null 2>&1
bash "$WT" rm featdev  >/dev/null 2>&1
t "rm removes everything" test "$(ls "$TMP/wtroot" 2>/dev/null | wc -l | tr -d ' ')" = 0

echo
echo "smoke: $pass passed, $fail failed"
exit "$fail"
