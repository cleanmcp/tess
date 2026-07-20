#!/usr/bin/env python3
"""tess resume [--plain] [--refresh] — list recent Claude + Kimi sessions (any
folder) with a one-line AI summary of what each was actually working on, pick
one, and resume it in its original folder.

Summaries come from the local model (ollama, med tier) and are cached, so the
list is instant after the first run. --plain skips AI (raw titles); --refresh
regenerates. If a session's folder was deleted, tess offers to recreate it —
both claude and kimi key sessions on the working directory, so resuming from
anywhere else fails."""
import os, sys, glob, json, time, re, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_common import C, short  # noqa: E402

HOME = os.path.expanduser("~")
LIMIT = 30
CACHE = os.path.join(HOME, ".local/share/tess/resume-summaries.json")
PLAIN = "--plain" in sys.argv
REFRESH = "--refresh" in sys.argv


def to_epoch(v, fallback):
    if isinstance(v, (int, float)):
        return v / 1000 if v > 1e12 else float(v)
    if isinstance(v, str):
        s = v.strip()
        if s.replace(".", "", 1).isdigit():
            f = float(s); return f / 1000 if f > 1e12 else f
        try:
            from datetime import datetime
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except Exception:
            return fallback
    return fallback


def ago(ts):
    s = max(0, int(time.time() - ts))
    for n, u in ((86400, "d"), (3600, "h"), (60, "m")):
        if s >= n:
            return f"{s // n}{u}"
    return f"{s}s"


# ---- gather: each session = dict(ts, tool, cwd, title, detail, sid, mtime) ----
sessions = []

# Claude: ~/.claude/projects/<proj>/<sid>.jsonl — AI title if present, else first
# prompt; the last assistant text feeds the summary.
for f in sorted(glob.glob(f"{HOME}/.claude/projects/*/*.jsonl"),
                key=os.path.getmtime, reverse=True)[:LIMIT]:
    cwd = title = first = last_a = None
    try:
        with open(f, errors="ignore") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") == "ai-title" and d.get("aiTitle"):
                    title = d["aiTitle"]
                if not cwd and d.get("cwd"):
                    cwd = d["cwd"]
                c = (d.get("message") or {}).get("content")
                if isinstance(c, list):
                    c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                if not isinstance(c, str) or not c.strip():
                    continue
                if d.get("type") == "user" and not first and not c.strip().startswith(("<", "!", "/")):
                    first = c.strip()
                elif d.get("type") == "assistant":
                    last_a = c.strip()
    except Exception:
        pass
    detail = " | ".join(x for x in (
        ("task: " + (title or first or ""))[:260] if (title or first) else "",
        ("ended on: " + " ".join(last_a.split())[-260:]) if last_a else "") if x)
    sessions.append({"ts": os.path.getmtime(f), "tool": "claude", "cwd": cwd,
                     "title": title or first or "(no summary)", "detail": detail,
                     "sid": os.path.basename(f)[:-6], "mtime": os.path.getmtime(f)})

# Kimi: ~/.kimi-code/session_index.jsonl is the source of truth — it holds the
# EXACT session id `kimi -S` accepts (old `session_*` and new `ses_*` formats
# alike; never strip the prefix) plus the working directory the session is
# keyed to. Titles come from each session's state.json.
kimi_index = os.path.join(HOME, ".kimi-code", "session_index.jsonl")
try:
    for line in open(kimi_index, errors="ignore"):
        try:
            e = json.loads(line)
        except Exception:
            continue
        sid, sdir, wd = e.get("sessionId"), e.get("sessionDir"), e.get("workDir")
        if not sid or not sdir:
            continue
        st = {}
        try:
            st = json.load(open(os.path.join(sdir, "state.json")))
        except Exception:
            pass
        mt = os.path.getmtime(sdir) if os.path.isdir(sdir) else 0
        ts = to_epoch(st.get("updatedAt") or st.get("createdAt"), mt)
        title = st.get("title") or st.get("lastPrompt") or "(untitled)"
        detail = ("task: " + title[:260]) if title != "(untitled)" else ""
        sessions.append({"ts": ts, "tool": "kimi", "cwd": wd, "title": title,
                         "detail": detail, "sid": sid, "mtime": mt})
except OSError:
    pass  # kimi not installed / never used

sessions.sort(key=lambda s: s["ts"], reverse=True)
sessions = sessions[:LIMIT]
if not sessions:
    print("no saved sessions found."); sys.exit(0)


# ---- one-line AI summaries (local model, cached) ----
def load_cache():
    try:
        return json.load(open(CACHE))
    except Exception:
        return {}


def model_for(tier, default):
    try:
        for line in open(os.path.join(HOME, ".config/tess/models")):
            if line.startswith(tier + "="):
                return line.split("=", 1)[1].strip() or default
    except OSError:
        pass
    return default


def ollama_up():
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=0.8)
        return True
    except Exception:
        return False


def ollama(prompt, timeout=45):
    body = json.dumps({"model": model_for("med", "llama3.2:3b"), "prompt": prompt,
                       "stream": False, "options": {"temperature": 0.1}}).encode()
    r = urllib.request.urlopen(urllib.request.Request(
        "http://localhost:11434/api/generate", body,
        {"Content-Type": "application/json"}), timeout=timeout)
    return json.loads(r.read())["response"].strip()


def summarize(pending):
    """pending: list of session dicts -> {sid: one-liner}. Best-effort: any
    chunk that fails to parse just keeps its fallback titles."""
    out = {}
    CHUNK = 8
    for i in range(0, len(pending), CHUNK):
        batch = pending[i:i + CHUNK]
        items = "\n".join(f"{n}. {s['detail'][:260]}" for n, s in enumerate(batch, 1))
        prompt = (f"Below are {len(batch)} AI coding sessions (their task and how they "
                  f"ended). For EACH, write one line, max 8 words, saying what WORK was "
                  f"done — the thing built/fixed/investigated. Never output shell "
                  f"commands, paths, or the words 'folder'/'session'. No quotes. Output "
                  f"EXACTLY {len(batch)} lines: '1. <line>' through '{len(batch)}. <line>', "
                  f"nothing else.\n\n{items}")
        try:
            resp = ollama(prompt)
        except Exception:
            return out
        lines = {}
        for m in re.finditer(r"^\s*(\d+)[.)]\s*(.+)$", resp, re.M):
            lines[int(m.group(1))] = m.group(2).strip().strip('"')
        for n, s in enumerate(batch, 1):
            if lines.get(n) and len(lines[n]) > 3:
                out[s["sid"]] = " ".join(lines[n].split())[:80]
    return out


cache = load_cache()
for s in sessions:
    hit = cache.get(s["sid"])
    s["summary"] = hit["s"] if hit and hit.get("m") == s["mtime"] and not REFRESH else None

pending = [s for s in sessions if s["summary"] is None and len(s["detail"]) >= 18]
if not PLAIN and pending and (sys.stdin.isatty() or REFRESH) and ollama_up():
    print(f"  {C.grey}summarizing {len(pending)} session(s) with the local model "
          f"(cached after this)…{C.r}", flush=True)
    got = summarize(pending)
    for s in pending:
        if s["sid"] in got:
            s["summary"] = got[s["sid"]]
            cache[s["sid"]] = {"m": s["mtime"], "s": s["summary"]}
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        keep = {s["sid"] for s in sessions}
        json.dump({k: v for k, v in cache.items() if k in keep}, open(CACHE, "w"))
    except Exception:
        pass


# ---- render ----
print(f"\n  {C.bold}{C.mag}recent sessions{C.r} {C.grey}(newest first · any folder){C.r}\n")
for i, s in enumerate(sessions, 1):
    tcol = C.yellow if s["tool"] == "kimi" else C.cyan
    fold = (s["cwd"] or "?").replace(HOME, "~")
    gone = f" {C.red}✗dir{C.r}" if s["cwd"] and not os.path.isdir(s["cwd"]) else ""
    line = s["summary"] or s["title"]
    print(f"  {C.bold}{i:>2}{C.r}  {tcol}{s['tool']:<6}{C.r} {C.grey}{ago(s['ts']):>4}{C.r}  "
          f"{C.green}{short(line, 44):<44}{C.r} {C.grey}{short(fold, 24)}{C.r}{gone}")

if not sys.stdin.isatty():   # agent/pipe: show the list, don't hang on input
    print(f"\n  {C.grey}(run `tess resume` interactively to pick one · ✗dir = folder deleted){C.r}")
    sys.exit(0)
print(f"\n  {C.grey}pick a number (Enter to cancel):{C.r} ", end="")
try:
    choice = input().strip()
except (EOFError, KeyboardInterrupt):
    sys.exit(0)
if not choice.isdigit() or not (1 <= int(choice) <= len(sessions)):
    print("  cancelled."); sys.exit(0)

s = sessions[int(choice) - 1]
wd = s["cwd"]
# both tools key sessions on their working directory — resuming from anywhere
# else fails ("Session not found"), so land there first, recreating if needed.
if wd and not os.path.isdir(wd):
    print(f"  {C.yellow}that session's folder is gone:{C.r} {wd}")
    try:
        ans = input("  recreate it and resume there? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)
    if not ans.startswith("y"):
        print("  cancelled."); sys.exit(0)
    try:
        os.makedirs(wd)
    except OSError as e:
        print(f"  couldn't recreate it: {e}"); sys.exit(1)
if wd and os.path.isdir(wd):
    os.chdir(wd)

if s["tool"] == "claude":
    print(f"  {C.grey}resuming claude in {wd or os.getcwd()}…{C.r}")
    try:
        os.execvp("claude", ["claude", "--resume", s["sid"]])
    except FileNotFoundError:
        print("  claude CLI not found on PATH."); sys.exit(1)
else:
    print(f"  {C.grey}resuming kimi in {wd or os.getcwd()}…{C.r}")
    try:
        os.execvp("kimi", ["kimi", "-S", s["sid"]])
    except FileNotFoundError:
        print("  kimi CLI not found on PATH."); sys.exit(1)
