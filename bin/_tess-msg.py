#!/usr/bin/env python3
"""tess messages [query] — recent iMessages/SMS incl. group chats, with contact names.
Read-only. Needs Full Disk Access."""
import os, sys, sqlite3, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tess_common import C, resolve, short, decode_body, chat_labels  # noqa: E402

DB = os.path.expanduser("~/Library/Messages/chat.db")
q = " ".join(sys.argv[1:]).strip()
ql = q.lower()

def die_perm():
    print("can't read Messages — grant Full Disk Access to cmux, then restart cmux.")
    sys.exit(1)

try:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
except Exception:
    die_perm()

try:
    labels = chat_labels(con)
    rows = con.execute("""
        SELECT m.date, m.is_from_me, m.text, m.attributedBody, sh.id, cmj.chat_id
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        LEFT JOIN handle sh ON m.handle_id = sh.ROWID
        ORDER BY m.date DESC LIMIT 900
    """).fetchall()
except sqlite3.OperationalError:
    die_perm()

def when(ts):
    try:
        return datetime.datetime.fromtimestamp(ts / 1e9 + 978307200).strftime("%b %d %H:%M")
    except Exception:
        return "?"

print(f"\n  {C.bold}{C.mag}{'messages · ' + q if q else 'recent messages'}{C.r}\n")
shown = 0
for nsdate, from_me, text, body, sender_id, chat_id in rows:
    msg = text or decode_body(body)
    if not msg:
        continue
    who = labels.get(chat_id) or resolve(sender_id) or "unknown"
    is_group = who.startswith("👥")
    sender = resolve(sender_id) if (is_group and not from_me) else None
    if ql and ql not in who.lower() and ql not in (sender or "").lower() \
            and ql not in (sender_id or "").lower() and ql not in msg.lower():
        continue
    arrow = f"{C.green}→{C.r}" if from_me else f"{C.yellow}←{C.r}"
    label = short(who, 20)
    tail = f"{C.grey}{short(sender,12)}:{C.r} {short(msg,44)}" if sender else short(msg, 58)
    print(f"  {C.grey}{when(nsdate):>12}{C.r} {arrow} {C.cyan}{label:<20}{C.r} {tail}")
    shown += 1
    if shown >= 25:
        break
if shown == 0:
    print(f"  {C.grey}no messages found.{C.r}")
print()
