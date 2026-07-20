#!/usr/bin/env python3
"""tess calls — recent call history from the local CallHistory DB, with contact names.
Read-only. Needs Full Disk Access granted to your terminal app."""
import os, sys, sqlite3, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_common import C, resolve, short  # noqa: E402

DB = os.path.expanduser("~/Library/Application Support/CallHistoryDB/CallHistory.storedata")

try:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute("""
        SELECT ZADDRESS, ZDATE, ZDURATION, ZORIGINATED, ZANSWERED
        FROM ZCALLRECORD ORDER BY ZDATE DESC LIMIT 30
    """).fetchall()
except Exception:
    print("can't read call history — grant Full Disk Access to your terminal app:")
    print("  System Settings → Privacy & Security → Full Disk Access → enable your terminal, then restart it.")
    sys.exit(1)

def when(z):
    try:
        return datetime.datetime.fromtimestamp(z + 978307200).strftime("%b %d %H:%M")
    except Exception:
        return "?"

def num(a):
    if isinstance(a, bytes):
        a = a.decode("utf-8", "ignore")
    return resolve((a or "").strip()) or "unknown"

def dur(sec):
    sec = int(sec or 0)
    if sec <= 0:
        return "—"
    return f"{sec // 60}m{sec % 60:02d}s" if sec >= 60 else f"{sec}s"

print(f"\n  {C.bold}{C.mag}recent calls{C.r}\n")
for addr, zdate, zdur, orig, answered in rows:
    arrow = f"{C.green}→ out {C.r}" if orig else (
        f"{C.yellow}← in  {C.r}" if answered else f"{C.red}✗ miss{C.r}")
    print(f"  {C.grey}{when(zdate):>12}{C.r} {arrow}  {C.cyan}{short(num(addr),22):<22}{C.r} {C.grey}{dur(zdur)}{C.r}")
print()
