#!/usr/bin/env python3
# tess claude|kimi [feat|.] ["prompt"] [flags] — spawn an hcom-coordinated
# agent with its task, model and effort GUARANTEED, not just requested.
#
#   feat         create/enter that worktree (via worktree.sh); '.' = current dir
#   "prompt"     the agent's first task (or --file/-f <path>)
#   --model M    model at launch — verified applied, both claude and kimi
#   --effort E   effort/thinking level — verified applied
#   --tag T      hcom group tag (default: feat, so names read feat-xxxx)
#   --auto       start ALREADY in auto permission mode (no per-command
#                approval prompts; claude: --permission-mode auto, kimi:
#                --auto) — verified on the running agent's footer
#   --readonly   ENFORCED read-only role (claude: --permission-mode plan,
#                kimi: --plan) — not just prompt text
#   --can-deploy allow deploy commands (default: a curated deny-list of
#                deploy-ish Bash patterns is enforced via --disallowedTools;
#                override the list with TESS_DEPLOY_DENY in config)
#   --budget N   hard spend cap in USD (claude --max-budget-usd; recorded
#                for tess spend)
#   --no-auto-trust  don't answer the folder-trust dialog automatically
#   --dry-run    print the exact plan, do nothing
#
# Why the dance: launch flags like --model have been observed NOT to stick
# through hcom's PTY launch. So the spawner launches bare, waits for the agent,
# answers the trust dialog (tess just created that worktree — trusting it is
# the user's intent), applies /model + /effort via the reliable injector, and
# VERIFIES each on screen before finally injecting the prompt (transcript-
# confirmed). Order guaranteed: trust → model → effort → prompt.
import os
import functools
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
print = functools.partial(print, flush=True)
from tess_agents import AgentError, inject, launch, press, screen_text, term_state

WORKTREE_ROOT = os.environ.get("TESS_WORKTREE_ROOT") or os.path.expanduser("~/worktrees")
LIBEXEC = os.environ.get("TESS_LIB") or os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
RESERVED = set((os.environ.get("TESS_RESERVED") or "").split())

# friendly → real model ids (anything unknown passes through untouched)
CLAUDE_MODELS = {"fable": "claude-fable-5", "fable5": "claude-fable-5",
                 "fable-5": "claude-fable-5"}

# deploy-ish commands denied unless --can-deploy (claude permission patterns)
DEPLOY_DENY = (os.environ.get("TESS_DEPLOY_DENY") or
               "Bash(gcloud run deploy:*),Bash(gcloud app deploy:*),"
               "Bash(gcloud builds submit:*),Bash(vercel deploy:*),"
               "Bash(vercel --prod:*),Bash(kubectl apply:*),"
               "Bash(terraform apply:*),Bash(fly deploy:*),"
               "Bash(gh pr merge:*)").split(",")
BUDGETS = os.path.expanduser("~/.config/tess/state/budgets.json")


def record_budget(name, tool, model, budget):
    import json
    try:
        data = json.load(open(BUDGETS))
    except (OSError, ValueError):
        data = {}
    data[name] = {"tool": tool, "model": model, "budget_usd": budget,
                  "started": __import__("time").strftime("%F %T")}
    os.makedirs(os.path.dirname(BUDGETS), exist_ok=True)
    json.dump(data, open(BUDGETS, "w"), indent=1)


def die(msg, code=1):
    print(f"tess: {msg}", file=sys.stderr)
    sys.exit(code)


def valid_feat(n):
    if n.startswith("-") or n.startswith(".") or "/" in n:
        return False
    if n in RESERVED:
        return False
    return all(c.isalnum() or c in "._-" for c in n)


def screen_has(agent, needle):
    return needle.lower() in screen_text(term_state(agent)).lower()


def kimi_display_name(alias):
    """A kimi model's picker/footer name comes from config.toml display_name."""
    import re
    try:
        txt = open(os.path.expanduser("~/.kimi-code/config.toml")).read()
    except OSError:
        return None
    m = re.search(r'\[models\."%s"\](.*?)(?=\n\[|\Z)' % re.escape(alias), txt, re.S)
    if m:
        d = re.search(r'display_name\s*=\s*"([^"]+)"', m.group(1))
        if d:
            return d.group(1)
    return None


def kimi_set_model(agent, alias):
    """Fix path when `kimi -m` didn't stick: drive the model picker with keys.
    /model → Enter → search by display name → Enter → (Thinking page) Enter."""
    name = kimi_display_name(alias) or alias.split("/")[-1]
    press(agent, "esc")
    press(agent, "/model")
    press(agent, "enter")
    if not screen_has(agent, "select a model"):
        return False
    press(agent, name)
    press(agent, "enter")           # select top match
    if screen_has(agent, "thinking"):
        press(agent, "enter")       # accept the thinking toggle page
    press(agent, "esc")             # make sure no picker remnants linger
    return screen_has(agent, name)


def kimi_footer(agent):
    lines = [l for l in (term_state(agent) or {}).get("lines", []) if l.strip()]
    return "\n".join(lines[-3:]).lower()


def main():
    args = sys.argv[1:]
    if not args:
        die("usage: tess claude|kimi [feat|.] [\"prompt\"] [--model M] [--effort E]")
    tool = args.pop(0)
    if tool not in ("claude", "kimi"):
        die(f"unknown tool '{tool}' (claude or kimi)")

    feat = prompt = pfile = model = effort = tag = budget = None
    auto_trust, dry = True, False
    readonly = can_deploy = auto_mode = False
    pos = []

    def val(i):
        if i + 1 >= len(args):
            die(f"{args[i]} needs a value")
        return args[i + 1]

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--file", "-f"):
            pfile = val(i)
            i += 1
        elif a == "--model":
            model = val(i)
            i += 1
        elif a == "--effort":
            effort = val(i)
            i += 1
        elif a == "--tag":
            tag = val(i)
            i += 1
        elif a == "--budget":
            budget = val(i)
            i += 1
        elif a in ("--auto", "--auto-mode"):
            auto_mode = True
        elif a == "--readonly":
            readonly = True
        elif a == "--can-deploy":
            can_deploy = True
        elif a == "--no-auto-trust":
            auto_trust = False
        elif a == "--dry-run":
            dry = True
        elif a.startswith("-") and a != ".":
            die(f"unknown flag '{a}' (help: tess help {tool})")
        else:
            pos.append(a)
        i += 1
    if len(pos) > 2:
        die("too many arguments — quote the prompt: tess claude <feat> \"<prompt>\"")
    if pos:
        feat = pos[0]
    if len(pos) == 2:
        prompt = pos[1]
    if pfile:
        if prompt:
            die("give a prompt either inline or via --file, not both")
        try:
            with open(pfile) as f:
                prompt = f.read().strip()
        except OSError as e:
            die(f"can't read --file: {e}")

    def narrow_single_repo(d):
        """A single-repo feature's agent belongs INSIDE the repo, not in the
        folder shell around it (multi-repo features keep the root + AGENTS.md)."""
        if not os.path.isdir(d) or os.path.exists(os.path.join(d, ".git")):
            return d
        subs = [os.path.join(d, s) for s in sorted(os.listdir(d))
                if os.path.exists(os.path.join(d, s, ".git"))]
        return subs[0] if len(subs) == 1 else d

    if feat and feat != ".":
        if not valid_feat(feat):
            die(f"'{feat}' is not a valid feature name", 2)
        wdir = narrow_single_repo(os.path.join(WORKTREE_ROOT, feat))
        tag = tag or feat
    else:
        wdir = os.getcwd()

    if tool == "claude" and model:
        model = CLAUDE_MODELS.get(model.lower(), model)
    tool_args = []
    roles = []
    if model:
        # best effort at launch; verified (and fixed) after the agent is up
        tool_args += (["-m", model] if tool == "kimi" else ["--model", model])
    if readonly and auto_mode:
        die("--readonly and --auto contradict each other — pick one")
    if readonly:
        # ENFORCED by the tool's own permission system, not prompt text
        tool_args += ["--plan"] if tool == "kimi" else ["--permission-mode", "plan"]
        roles.append("readonly (enforced: " + ("kimi --plan" if tool == "kimi"
                     else "claude --permission-mode plan") + ")")
    if auto_mode:
        tool_args += ["--auto"] if tool == "kimi" else ["--permission-mode", "auto"]
        roles.append("auto mode (no per-command approval prompts; verified on footer)")
    if budget:
        if tool == "claude":
            tool_args += ["--max-budget-usd", str(budget)]
            roles.append(f"budget ${budget} (enforced: --max-budget-usd)")
        else:
            roles.append(f"budget ${budget} ⚠ kimi has no spend cap — recorded only")
    if not can_deploy and not readonly and tool == "claude":
        tool_args += ["--disallowedTools", *DEPLOY_DENY]
        roles.append(f"no-deploy (enforced: {len(DEPLOY_DENY)} denied Bash patterns; "
                     f"lift with --can-deploy)")
    elif can_deploy:
        roles.append("can-deploy (deny-list lifted)")

    if dry:
        print(f"would spawn: {tool} in {wdir}" + (f" [tag {tag}]" if tag else ""))
        if feat and feat != "." and not os.path.isdir(wdir):
            print(f"would create worktree: {feat}")
        print(f"  launch args: {tool_args or '(none)'}")
        for r in roles:
            print(f"  role: {r}")
        if model:
            print(f"  then verify model = {model} (fix via /model + screen check)")
        if effort:
            print(f"  then verify effort = {effort} (fix via /effort + screen check)")
        if prompt:
            print(f"  then inject prompt ({len(prompt)} chars, transcript-confirmed)")
        return

    if feat and feat != "." and not os.path.isdir(wdir):
        print(f"creating worktree '{feat}'…")
        r = subprocess.run(["bash", os.path.join(LIBEXEC, "worktrees", "worktree.sh"), feat])
        if r.returncode != 0:
            die(f"worktree creation failed for '{feat}'")
        wdir = narrow_single_repo(wdir)

    print(f"spawning {tool} in {wdir}…")
    try:
        name = launch(tool, wdir, tag=tag, tool_args=tool_args)
        print(f"  agent: {name}")
        for r in roles:
            print(f"  {r}")
        if budget or readonly:
            record_budget(name, tool, model, budget)

        # settle + clear the trust dialog before anything else
        inject_kw = dict(auto_trust=auto_trust)
        applied = []
        if model and tool == "claude":
            # /model <id> prints "Set model to …" — that line is the proof
            inject(name, f"/model {model}", raw=True, expect=None, **inject_kw)
            if screen_has(name, "set model") or screen_has(name, model):
                applied.append(f"model={model} ✓verified")
            else:
                applied.append(f"model={model} ⚠ UNVERIFIED — check the pane (tess agents)")
        elif model:  # kimi: -m at launch; the footer shows the display name
            from tess_agents import wait_ready
            wait_ready(name, timeout=90, auto_trust=auto_trust)
            needle = kimi_display_name(model) or model.split("/")[-1]
            ok = needle.lower() in kimi_footer(name) or kimi_set_model(name, model)
            applied.append(f"model={model} ({needle}) " +
                           ("✓verified" if ok else f"⚠ UNVERIFIED — check the pane (tess agents)"))
        if auto_mode:
            # proof, not hope: the running agent's footer must say auto mode
            from tess_agents import wait_ready
            wait_ready(name, timeout=90, auto_trust=auto_trust)
            if "auto" in kimi_footer(name):
                applied.append("auto mode ✓verified (footer)")
            else:
                applied.append(f"auto mode ⚠ UNVERIFIED — check the pane (tess agents)")
        if effort and tool == "claude":
            inject(name, f"/effort {effort}", raw=True, expect=None, **inject_kw)
            if screen_has(name, effort):
                applied.append(f"effort={effort} ✓verified")
            else:
                applied.append(f"effort={effort} ⚠ UNVERIFIED — check the pane (tess agents)")
        elif effort:
            # kimi's effort control is its thinking toggle, shown in the footer
            from tess_agents import wait_ready
            wait_ready(name, timeout=90, auto_trust=auto_trust)
            want = effort.lower() not in ("low", "off", "none", "min")
            have = "thinking" in kimi_footer(name)
            if want == have:
                applied.append(f"effort={effort} ✓verified (kimi thinking {'on' if have else 'off'})")
            else:
                applied.append(f"effort={effort} ⚠ kimi thinking is {'on' if have else 'off'} and this "
                               f"model can't switch — pick a different kimi model if this matters")
        for a in applied:
            print(f"  {a}")
        if prompt:
            print("  " + inject(name, prompt, **inject_kw))
        print(f"✓ {name} ready in {wdir}")
        print(f"  follow along: tess report {name} · tess agents · tess tell {name} -- <msg>")
    except AgentError as e:
        die(e.msg, e.code)


if __name__ == "__main__":
    main()
