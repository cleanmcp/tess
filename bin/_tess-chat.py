#!/usr/bin/env python3
"""tess chat <name|group> — full conversation (1:1 or group) with inline image previews.
Read-only. Needs Full Disk Access. Images render via chafa in a real terminal."""
import os, sys, sqlite3, subprocess, tempfile, datetime, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tess_common import C, resolve, short, decode_body, chat_labels  # noqa: E402

DB = os.path.expanduser("~/Library/Messages/chat.db")
q = " ".join(sys.argv[1:]).strip()
if not q:
    print("usage: tess chat <name or group>"); sys.exit(1)

try:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
except Exception:
    print("can't read Messages — grant Full Disk Access to cmux, then restart cmux."); sys.exit(1)

labels = chat_labels(con)
ql = q.lower()
matching = [cid for cid, lab in labels.items() if ql in lab.lower()]
if not matching:
    # try matching by number/handle
    matching = [cid for cid, lab in labels.items()]  # fall through; filter by handle below
    hits = con.execute("""SELECT DISTINCT cmj.chat_id FROM message m
        JOIN chat_message_join cmj ON cmj.message_id=m.ROWID
        JOIN handle h ON m.handle_id=h.ROWID WHERE h.id LIKE ?""", (f"%{q}%",)).fetchall()
    matching = [r[0] for r in hits]
if not matching:
    print(f"no conversation found for '{q}'."); sys.exit(0)

# among matches, pick the most recently active chat
last = dict(con.execute(f"""
    SELECT cmj.chat_id, MAX(m.date) FROM message m
    JOIN chat_message_join cmj ON cmj.message_id=m.ROWID
    WHERE cmj.chat_id IN ({','.join('?'*len(matching))}) GROUP BY cmj.chat_id
""", matching).fetchall())
if not last:
    print(f"no messages for '{q}'."); sys.exit(0)
chat_id = max(last, key=last.get)
title = labels.get(chat_id, q)
others = [labels[c] for c in matching if c != chat_id and c in last]

rows = con.execute("""
    SELECT m.date, m.is_from_me, m.text, m.attributedBody, sh.id, a.filename, a.mime_type
    FROM message m
    JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
    LEFT JOIN handle sh ON m.handle_id = sh.ROWID
    LEFT JOIN message_attachment_join maj ON maj.message_id = m.ROWID
    LEFT JOIN attachment a ON a.ROWID = maj.attachment_id
    WHERE cmj.chat_id = ?
    ORDER BY m.date DESC LIMIT 140
""", (chat_id,)).fetchall()
rows = list(reversed(rows))[-70:]

def when(ns):
    try:
        return datetime.datetime.fromtimestamp(ns / 1e9 + 978307200)
    except Exception:
        return None

def show_image(path, mime):
    p = os.path.expanduser(path or "")
    if not p or not os.path.exists(p):
        return f"{C.grey}🖼 [image not downloaded]{C.r}"
    if not sys.stdout.isatty() or not shutil.which("chafa"):
        return f"{C.blue}🖼 {os.path.basename(p)}{C.r}  {C.grey}{p}{C.r}"
    render = p
    if (mime or "").endswith("heic") or p.lower().endswith(".heic"):
        tmp = tempfile.mktemp(suffix=".png")
        if subprocess.run(["sips", "-s", "format", "png", p, "--out", tmp], capture_output=True).returncode == 0:
            render = tmp
    try:
        img = subprocess.run(["chafa", "--size", "44x18", "--animate", "off", render],
                             capture_output=True, text=True, timeout=15).stdout
    except Exception:
        img = ""
    return f"{C.grey}🖼 {os.path.basename(p)}  (open: {p}){C.r}\n{img}"

hdr = f"💬 {title}"
print(f"\n  {C.bold}{C.mag}{hdr}{C.r}  {C.grey}(last {len(rows)} messages){C.r}")
if others:
    print(f"  {C.grey}other matches: {', '.join(short(o,18) for o in others[:3])}{C.r}")
print()
last_day = None
for ns, from_me, text, body, sender_id, fname, mime in rows:
    dt = when(ns)
    day = dt.strftime("%a %b %d") if dt else "?"
    if day != last_day:
        print(f"  {C.grey}── {day} ──{C.r}"); last_day = day
    tm = dt.strftime("%H:%M") if dt else ""
    tag = f"{C.green}you{C.r}" if from_me else f"{C.cyan}{short(resolve(sender_id) or '?', 16)}{C.r}"
    if fname and (mime or "").startswith("image"):
        out = show_image(fname, mime)
    elif fname:
        out = f"{C.blue}📎 {os.path.basename(fname)}{C.r}"
    else:
        out = text or decode_body(body) or ""
    if not out.strip():
        continue
    print(f"  {C.grey}{tm}{C.r} {tag}: {out}")
print()
