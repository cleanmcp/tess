#!/usr/bin/env python3
# tess team <spec.yaml|-> [--dry-run] [--parallel] — one-command fan-out:
# spawn a whole fleet across worktrees, each agent with its own prompt, model,
# effort and role template. Spec:
#
#   defaults:                  # optional, applied to every agent
#     tool: claude             # claude | kimi
#     model: fable5
#     effort: high
#     template: implement      # templates/<name>.md (user dir wins)
#   agents:
#     - feature: auth-fix      # worktree to create/use ('.' = current dir)
#       prompt: |
#         Fix the login redirect loop.
#       model: opus            # any per-agent override of the defaults
#       template: investigate
#       count: 2               # optional: N copies of this agent
#
# Templates live in ~/.config/tess/templates/ (yours) and <repo>/templates/
# (built-in: investigate, implement, review). The template text is prepended
# to the prompt so roles like "read-only investigator" are consistent.
# Every spawn goes through the verified spawner (trust dialog answered,
# model/effort CONFIRMED applied, prompt transcript-confirmed).
import functools
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

print = functools.partial(print, flush=True)

TESS_BIN = os.environ.get("TESS_BIN") or os.path.dirname(os.path.realpath(__file__))
USER_TPL = os.path.expanduser("~/.config/tess/templates")
REPO_TPL = os.path.join(os.path.dirname(TESS_BIN), "templates")


def die(msg, code=1):
    print(f"tess team: {msg}", file=sys.stderr)
    sys.exit(code)


def load_template(name):
    if not name or name == "none":
        return ""
    for d in (USER_TPL, REPO_TPL):
        p = os.path.join(d, f"{name}.md")
        if os.path.isfile(p):
            return open(p).read().strip()
    avail = sorted({f[:-3] for d in (USER_TPL, REPO_TPL) if os.path.isdir(d)
                    for f in os.listdir(d) if f.endswith(".md")})
    die(f"no template '{name}' (available: {', '.join(avail) or 'none'})")


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    parallel = "--parallel" in args
    pos = [a for a in args if not a.startswith("-") or a == "-"]
    if len(pos) != 1:
        die("usage: tess team <spec.yaml|-> [--dry-run] [--parallel]")
    src = pos[0]
    try:
        text = sys.stdin.read() if src == "-" else open(src).read()
    except OSError as e:
        die(f"can't read spec: {e}")

    try:
        import yaml
        spec = yaml.safe_load(text)
    except ImportError:
        die("python3 needs pyyaml for tess team (pip3 install pyyaml)")
    except Exception as e:
        die(f"bad YAML: {e}")
    if not isinstance(spec, dict) or not isinstance(spec.get("agents"), list) or not spec["agents"]:
        die("spec needs an 'agents:' list (see: tess help team)")

    defaults = spec.get("defaults") or {}
    jobs = []
    for i, a in enumerate(spec["agents"], 1):
        if not isinstance(a, dict):
            die(f"agents[{i}] must be a mapping")
        cfg = {**defaults, **a}
        tool = cfg.get("tool", "claude")
        if tool not in ("claude", "kimi"):
            die(f"agents[{i}]: unknown tool '{tool}'")
        feat = cfg.get("feature") or cfg.get("feat") or "."
        prompt = (cfg.get("prompt") or "").strip()
        if not prompt:
            die(f"agents[{i}] ({feat}): needs a prompt")
        tpl = load_template(cfg.get("template"))
        full = (tpl + "\n\n## Your task\n" + prompt).strip() if tpl else prompt
        count = int(cfg.get("count", 1))
        for _ in range(count):
            cmd = ["python3", os.path.join(TESS_BIN, "_tess-spawn.py"), tool, str(feat), full]
            for k, flag in (("model", "--model"), ("effort", "--effort"),
                            ("tag", "--tag"), ("budget", "--budget")):
                if cfg.get(k):
                    cmd += [flag, str(cfg[k])]
            if cfg.get("readonly"):
                cmd.append("--readonly")
            if cfg.get("can_deploy") or cfg.get("can-deploy"):
                cmd.append("--can-deploy")
            if dry:
                cmd.append("--dry-run")
            jobs.append((feat, tool, cfg, cmd))

    print(f"team: {len(jobs)} agent(s)" + (" [DRY RUN]" if dry else ""))
    procs = []
    fails = 0
    for feat, tool, cfg, cmd in jobs:
        print(f"\n─ {tool} @ {feat}"
              + (f" · model {cfg.get('model')}" if cfg.get("model") else "")
              + (f" · effort {cfg.get('effort')}" if cfg.get("effort") else "")
              + (f" · template {cfg.get('template')}" if cfg.get("template") else ""))
        if parallel and not dry:
            procs.append((feat, subprocess.Popen(cmd)))
        else:
            r = subprocess.run(cmd)
            if r.returncode != 0:
                fails += 1
    for feat, p in procs:
        if p.wait() != 0:
            fails += 1
    if dry:
        print("\n(dry run — nothing spawned)")
        return
    print(f"\nteam up: {len(jobs) - fails}/{len(jobs)} spawned. "
          f"watch: tess status · tess digest · tess wait all")
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
