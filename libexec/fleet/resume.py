#!/usr/bin/env python3
"""tess resume — list recent Claude + Kimi sessions (any folder) with a real summary,
pick one, and resume it in its original folder."""
import os, sys, glob, json, time, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_common import C, short  # noqa: E402

HOME = os.path.expanduser("~")
LIMIT = 30


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


def kimi_cwd(session_dir):
    pat = re.compile(r'"cwd"\s*:\s*"([^"]+)"')
    cands = [os.path.join(session_dir, "agents", "main", "wire.jsonl")]
    cands += glob.glob(os.path.join(session_dir, "agents", "*", "wire.jsonl"))
    cands += glob.glob(os.path.join(session_dir, "logs", "*.log"))
    for c in cands:
        try:
            with open(c, errors="ignore") as fh:
                for i, line in enumerate(fh):
                    m = pat.search(line)
                    if m and m.group(1).startswith("/") and ".kimi-code" not in m.group(1):
                        return m.group(1)
                    if i > 300:
                        break
        except Exception:
            pass
    return None


sessions = []  # (ts, tool, folder, summary, kind, id, cwd, sdir)

# ---- Claude: prefer the AI-generated session title; fall back to first prompt ----
files = sorted(glob.glob(f"{HOME}/.claude/projects/*/*.jsonl"),
               key=os.path.getmtime, reverse=True)[:LIMIT]
for f in files:
    cwd = title = first = None
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
                if not first and d.get("type") == "user":
                    c = (d.get("message") or {}).get("content")
                    if isinstance(c, list):
                        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                    if isinstance(c, str) and c.strip() and not c.strip().startswith("<"):
                        first = c.strip()
    except Exception:
        pass
    sid = os.path.basename(f)[:-6]
    summ = title or first or "(no summary)"
    sessions.append((os.path.getmtime(f), "claude", cwd or "?", summ, "claude", sid, cwd, None))

# ---- Kimi: state.json title = its summary ----
for sf in glob.glob(f"{HOME}/.kimi-code/sessions/*/session_*/state.json"):
    try:
        d = json.load(open(sf))
    except Exception:
        continue
    ts = to_epoch(d.get("updatedAt") or d.get("createdAt"), os.path.getmtime(sf))
    title = d.get("title") or d.get("lastPrompt") or "(untitled)"
    sess_path = os.path.dirname(sf)
    uuid = os.path.basename(sess_path).replace("session_", "")
    wd = os.path.basename(os.path.dirname(sess_path))
    name = wd[3:].rsplit("_", 1)[0] if wd.startswith("wd_") else wd
    sessions.append((ts, "kimi", name, title, "kimi", uuid, None, sess_path))

sessions.sort(key=lambda x: x[0], reverse=True)
sessions = sessions[:LIMIT]

if not sessions:
    print("no saved sessions found."); sys.exit(0)

print(f"\n  {C.bold}{C.mag}recent sessions{C.r} {C.grey}(newest first · any folder){C.r}\n")
for i, (ts, tool, folder, summ, kind, sid, cwd, sdir) in enumerate(sessions, 1):
    tcol = C.yellow if tool == "kimi" else C.cyan
    fold = folder.replace(HOME, "~")
    print(f"  {C.bold}{i:>2}{C.r}  {tcol}{tool:<6}{C.r} {C.grey}{ago(ts):>4}{C.r}  "
          f"{C.green}{short(summ, 42):<42}{C.r} {C.grey}{short(fold, 26)}{C.r}")

if not sys.stdin.isatty():   # agent/pipe: show the list, don't hang on input
    print(f"\n  {C.grey}(run `tess resume` interactively to pick one){C.r}")
    sys.exit(0)
print(f"\n  {C.grey}pick a number (Enter to cancel):{C.r} ", end="")
try:
    choice = input().strip()
except (EOFError, KeyboardInterrupt):
    sys.exit(0)
if not choice.isdigit() or not (1 <= int(choice) <= len(sessions)):
    print("  cancelled."); sys.exit(0)

ts, tool, folder, summ, kind, sid, cwd, sdir = sessions[int(choice) - 1]
if kind == "claude":
    if cwd and os.path.isdir(cwd):
        os.chdir(cwd)
    print(f"  {C.grey}resuming claude in {cwd or folder}…{C.r}")
    os.execvp("claude", ["claude", "--resume", sid])
else:
    kc = kimi_cwd(sdir) if sdir else None
    if kc and os.path.isdir(kc):
        os.chdir(kc)
    print(f"  {C.grey}resuming kimi in {kc or folder}…{C.r}")
    os.execvp("kimi", ["kimi", "-S", sid])
