#!/usr/bin/env python3
# tess_agents.py — shared plumbing for tess's agent commands (inject/spawn/
# status/team). Everything talks to hcom; TESS_HCOM decides how to invoke it.
import json
import os
import re
import subprocess
import time

HCOM = (os.environ.get("TESS_HCOM") or "hcom").split()

# Client-facing branding: the user should only ever see "tess", never the
# backend. Two things leak: (1) the backend's own "vX.YZ available — run
# `... update`" nag banner (stderr), and (2) the [uvx hcom:<name>] tracking
# marker agents are told to echo in their first reply. Strip both wherever
# tess surfaces backend output. This is cosmetic only — the passthrough and
# update mechanism keep working.
_NAG_RE = re.compile(r"^.*hcom v[0-9][0-9.]* available.*$\n?", re.MULTILINE)
_MARK_RE = re.compile(r"\[(?:uvx )?hcom:[^\]]*\]")
_TOK_RE = re.compile(r"\buvx hcom\b|\bhcom\b")


def scrub(text):
    """Strip the backend's nag banner and [uvx hcom:name] markers from any
    string before it reaches the user. Safe on free-form report prose — only
    removes noise, never rewrites meaning."""
    if not text:
        return text
    return _MARK_RE.sub("", _NAG_RE.sub("", text)).strip()


def brand(text):
    """Like scrub(), plus rebrand the backend invocation token to 'tess'. Use
    ONLY for short activity/detail strings (an agent's current command shown in
    tess status/digest) — never on prose, where it could mangle content."""
    if not text:
        return text
    return _TOK_RE.sub("tess", scrub(text))


class AgentError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def hcom(*args, timeout=60):
    try:
        r = subprocess.run([*HCOM, *args], capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        r = subprocess.CompletedProcess(args, 124)
        r.stdout, r.stderr = "", str(e)
        return r
    # drop the nag banner so surfaced errors never leak the backend name
    if r.stderr:
        r.stderr = _NAG_RE.sub("", r.stderr)
    return r


def hcom_json(*args, timeout=60):
    r = hcom(*args, timeout=timeout)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def term_state(agent):
    return hcom_json("term", agent, "--json")


def screen_text(state):
    return "\n".join((state or {}).get("lines", []))


def status_of(agent):
    r = hcom("list", agent, "status")
    return r.stdout.strip() if r.returncode == 0 else None


def agent_info(agent):
    return hcom_json("list", agent, "--json")


def list_agents():
    return hcom_json("list", "--json") or []


def last_exchange(agent):
    r = hcom("transcript", agent, "--json", "--last", "1")
    try:
        ex = json.loads(r.stdout)
        return ex[-1] if ex else None
    except ValueError:
        return None


def wait_ready(agent, timeout=180, force=False, auto_trust=False):
    """Wait until `agent` can take keystrokes. The PTY `ready` flag is
    unreliable inside cmux panes (observed false even when idle), so the
    hook-driven status is the gate: listening == idle == safe to type.
    With auto_trust, answers the folder-trust dialog of a freshly spawned
    agent (tess just created that worktree — trusting it is the user's intent).
    Returns the final term state; raises AgentError otherwise."""
    deadline = time.time() + timeout
    state = None
    trusted = False
    no_pty = 0
    while time.time() < deadline:
        state = term_state(agent)
        if state is None:
            # a freshly launched agent's PTY takes a few seconds to register
            no_pty += 1
            if no_pty >= 8:
                raise AgentError(2, f"'{agent}' has no PTY screen (headless/vanilla agent?) — "
                                    f"use `tess tell {agent} -- <msg>` instead.")
            time.sleep(2)
            continue
        no_pty = 0
        # the trust dialog can be on screen BEFORE hooks flip status to blocked
        # (early status reads "listening") — so check the screen every pass
        scr = screen_text(state).lower()
        on_trust = "trust this folder" in scr or "trust the files" in scr
        if auto_trust and not trusted and on_trust:
            hcom("term", "inject", agent, "--enter")
            trusted = True
            time.sleep(2)
            continue
        st = status_of(agent)
        if (st == "blocked" or on_trust) and not force:
            raise AgentError(5, f"'{agent}' is BLOCKED on an approval prompt — "
                                f"use `tess approve {agent}` first (or --force).")
        if st in (None, "inactive"):
            raise AgentError(1, f"'{agent}' is not running (status: {st})")
        if state.get("ready") or st == "listening":
            return state
        time.sleep(2)
    tail = "\n  ".join(l for l in (state or {}).get("lines", [])[-5:] if l.strip())
    raise AgentError(3, f"'{agent}' never became ready within {timeout}s (still busy). "
                        f"Screen tail:\n  {tail}")


def inject(agent, text, timeout=180, retries=3, force=False, raw=False,
           expect=None, auto_trust=False):
    """Type `text` into agent's input box, submit, and CONFIRM it landed.
    Default confirmation: our prompt appears as a NEW transcript exchange.
    raw=True (slash commands — they never hit the transcript): confirmation is
    input-box-cleared, plus `expect` substring on screen when given.
    Returns a human confirmation string; raises AgentError on failure."""
    text = " ".join(text.split())  # PTY input is one line; \n would submit early
    if not text:
        raise AgentError(1, "empty message — nothing to inject")

    st = status_of(agent)
    if st is None:
        raise AgentError(1, f"no agent named '{agent}' (see: tess agents)")

    state = wait_ready(agent, timeout=timeout, force=force, auto_trust=auto_trust)
    if (state.get("input_text") or "").strip() and not force:
        raise AgentError(6, f"'{agent}' already has text in its input box "
                            f"({state['input_text'][:60]!r}) — --force to append anyway.")

    before = last_exchange(agent)
    before_pos = before["position"] if before else -1
    before_user = " ".join((before or {}).get("user", "").split())
    probe = text[:40]

    def landed():
        if raw:
            s = term_state(agent) or {}
            if probe in (s.get("input_text") or ""):
                return None  # still sitting in the box
            if expect and expect.lower() not in screen_text(s).lower():
                return None
            return f"✓ ran on {agent}" + (f" (screen shows {expect!r})" if expect else "")
        ex = last_exchange(agent)
        if not ex:
            return None
        u = " ".join(ex.get("user", "").split())
        # kimi merges an injected prompt into the current exchange's user text
        # instead of opening a new position — accept either form of proof
        if probe in u and (ex["position"] > before_pos or probe not in before_user):
            return f"✓ landed on {agent} (transcript #{ex['position']})"
        return None

    def typed(state):
        # some TUIs (kimi) never expose input_text — fall back to the screen,
        # where the input box is rendered as text
        return probe in ((state or {}).get("input_text") or "") \
            or probe in screen_text(state)

    # type, and verify the text really appeared (never type twice in a row
    # without checking — that would duplicate the message)
    for _ in range(retries):
        state = term_state(agent) or {}
        if typed(state):
            break
        hcom("term", "inject", agent, text)
        time.sleep(0.7)
    else:
        if not typed(term_state(agent)):
            raise AgentError(4, f"typed {retries}x but the text never appeared in "
                                f"'{agent}' input box")

    # submit, then confirm — not just "keys sent"
    for _ in range(retries):
        hcom("term", "inject", agent, "--enter")
        confirm_by = time.time() + 12
        while time.time() < confirm_by:
            ok = landed()
            if ok:
                return ok
            time.sleep(1.5)
            s = term_state(agent) or {}
            if probe in (s.get("input_text") or ""):
                break  # enter didn't take — go resubmit
    ok = landed()
    if ok:
        return ok
    raise AgentError(4, f"submitted to '{agent}' but could not confirm it landed after "
                        f"{retries} attempts — check `tess agents`")


def agents_under(path, agents=None):
    """Agents whose working directory sits inside `path` (the feature dir).
    Prefix-safe: 'foo' never matches an agent living in 'foo-bar'."""
    path = os.path.abspath(path).rstrip("/") + "/"
    out = []
    for a in (list_agents() if agents is None else agents):
        d = (a.get("directory") or "").rstrip("/") + "/"
        if d.startswith(path):
            out.append(a)
    return out


def press(agent, key):
    """Send a bare key: 'enter', 'esc', or literal text."""
    if key == "enter":
        hcom("term", "inject", agent, "--enter")
    elif key == "esc":
        hcom("term", "inject", agent, "\x1b")
    else:
        hcom("term", "inject", agent, key)
    time.sleep(0.8)


LAUNCH_NAME_RE = re.compile(r"(?:Launch ready|Still launching[^:]*): (\S+) \(")


def launch(tool, dir, tag=None, tool_args=(), timeout=90):
    """Launch one agent via hcom in a new pane at `dir`. Returns its hcom name.
    Never passes --hcom-prompt: the caller injects prompts through inject() so
    ordering (trust → model → effort → prompt) is guaranteed."""
    known = {a["name"] for a in list_agents()}
    t0 = time.time()
    cmd = ["1", tool, "--go", "--dir", dir]
    if tag:
        cmd += ["--tag", tag]
    r = hcom(*cmd, *tool_args, timeout=timeout)
    if r.returncode == 1:
        raise AgentError(1, f"agent launch failed: {(r.stderr or r.stdout).strip()[-300:]}")
    m = LAUNCH_NAME_RE.search(r.stdout or "")
    if m:
        name = m.group(1)
        full = [a["name"] for a in list_agents() if a["name"].endswith(name)]
        if full:
            return full[0]
    # fallback: poll for a new name (optionally tag-scoped)
    deadline = time.time() + timeout
    while time.time() < deadline:
        for a in list_agents():
            if a["name"] in known:
                continue
            if tag and a.get("tag") != tag:
                continue
            if a.get("created_at", 0) >= t0 - 5:
                return a["name"]
        time.sleep(2)
    raise AgentError(1, f"launched {tool} but never saw it register with the fleet")
