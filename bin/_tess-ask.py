#!/usr/bin/env python3
"""tess ask "<natural language>" — voice/NL router. Uses the local LLM to decide
what you meant, runs the right tess action or answers, and speaks it (macOS `say`).
Fully offline. Meant to pair with Wispr Flow dictation ("tess <whatever>")."""
import os, sys, re, json, glob, subprocess, urllib.request

HOME = os.path.expanduser("~")
req = " ".join(sys.argv[1:]).strip()
req = re.sub(r"^\s*(hey\s+)?tess[\s,:\-]*", "", req, flags=re.I).strip()  # drop wake word
if not req:
    print("(say something after 'tess')"); sys.exit(0)

def ollama(prompt, model="llama3.2:3b", system="", timeout=120):
    body = json.dumps({"model": model, "prompt": prompt, "system": system,
                       "stream": False, "options": {"temperature": 0.2}}).encode()
    r = urllib.request.urlopen(urllib.request.Request(
        "http://localhost:11434/api/generate", body, {"Content-Type": "application/json"}), timeout=timeout)
    return json.loads(r.read())["response"].strip()

def speak(text):
    text = text.strip()
    print("\n" + text + "\n")
    try:
        args = ["say", "-r", "205", text[:1200]]
        if os.environ.get("TESS_SPEAK_SYNC"):   # listen mode: block so mic doesn't hear the TTS
            subprocess.run(args)
        else:
            subprocess.Popen(args)
    except Exception:
        pass

def strip_ansi(s):
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", s)

ROUTER = """You are the router for `tess`, the user's personal CLI. Read his request and reply with EXACTLY ONE line, nothing else:

RUN <cmd>        run a tess command. Valid <cmd>: brief | people | companies | reminders | calls | calendar | messages <name> | read
SESSION <name>   he's asking what's going on / status of a past coding session (e.g. "kimi chat fix", "the gcp session")
NOTE <name>      he wants a note/person read (e.g. a person or topic)
ANSWER <text>    it's a general question, a word/definition, or about a book he's reading — answer it yourself, briefly and plainly

Rules: pick the single best one. If he says "what's going on" with no session named -> RUN brief. If unsure -> ANSWER."""

try:
    decision = ollama(req, system=ROUTER).splitlines()[0].strip()
except Exception:
    speak("Local model isn't reachable. Is ollama running?"); sys.exit(1)

VALID_RUN = {"brief", "people", "companies", "reminders", "calls", "calendar", "messages", "read"}
m = re.match(r"\s*(RUN|SESSION|NOTE|ANSWER)\b[:\-]?\s*(.*)", decision, re.I | re.S)
verb = m.group(1).upper() if m else "ANSWER"
rest = (m.group(2).strip() if m else decision).strip()

# repair common small-model misroutes, e.g. "RUN session kimi" or "RUN <unknown>"
if verb == "RUN":
    first = rest.split()[0].lower() if rest else ""
    if first == "session" or "session" in req.lower() and first not in VALID_RUN:
        verb = "SESSION"; rest = re.sub(r"\bsession\b", "", rest, flags=re.I).strip()
    elif first not in VALID_RUN:
        verb = "ANSWER"

if verb == "RUN":
    out = strip_ansi(subprocess.run(["tess"] + rest.split(), capture_output=True, text=True).stdout)
    if len(out) > 400:
        out = ollama(f"In 1-2 short spoken sentences, tell the user the gist of:\n{out[:2500]}", model="llama3.2:1b")
    speak(out or "Nothing to report.")

elif verb == "NOTE":
    out = strip_ansi(subprocess.run(["tess", rest], capture_output=True, text=True).stdout)
    speak(ollama(f"Summarize this note for the user in 2-3 spoken sentences:\n{out[:2500]}", model="llama3.2:1b")
          if out.strip() else f"No note found for {rest}.")

elif verb == "SESSION":
    stop = {"the", "session", "in", "whats", "what", "going", "on", "is", "a", "my", "status", "of", "for"}
    tokens = [t for t in re.findall(r"[a-z0-9]+", rest.lower()) if t not in stop and len(t) > 2]
    if not tokens:
        tokens = [t for t in re.findall(r"[a-z0-9]+", req.lower()) if t not in stop and len(t) > 2]
    def match(s):
        s = s.lower(); return any(t in s for t in tokens)
    name = " ".join(tokens)
    # find matching claude/kimi sessions, grab recent text, summarize
    texts = []
    for f in sorted(glob.glob(f"{HOME}/.claude/projects/*/*.jsonl"), key=os.path.getmtime, reverse=True):
        if match(f):
            try:
                lines = open(f, errors="ignore").readlines()[-40:]
                for ln in lines:
                    d = json.loads(ln)
                    c = (d.get("message") or {}).get("content")
                    if isinstance(c, list):
                        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                    if isinstance(c, str) and c.strip():
                        texts.append(c.strip()[:400])
            except Exception:
                pass
            break
    for sf in sorted(glob.glob(f"{HOME}/.kimi-code/sessions/*/session_*/state.json"), key=os.path.getmtime, reverse=True):
        wd = os.path.basename(os.path.dirname(os.path.dirname(sf))).lower().replace("-", "").replace("_", "")
        if match(wd):
            try:
                d = json.load(open(sf))
                texts.append(f"kimi session '{d.get('title','')}' — last: {d.get('lastPrompt','')}")
            except Exception:
                pass
            break
    if texts:
        blob = "\n".join(texts[-25:])[:3000]
        speak(ollama(f"the user asked what's going on in his '{name}' session. From this recent activity, tell them in 2-4 short spoken sentences where it's at and what's next:\n{blob}"))
    else:
        speak(f"I couldn't find a session matching {name}.")

else:  # ANSWER — let the model answer the real question well
    speak(ollama(f"Answer the user plainly and briefly (2-4 sentences, spoken style, no jargon): {req}"))
