#!/usr/bin/env python3
"""tess readpos [title] — current reading position + the text just-read and coming-up.
The reading companion calls this to give a live recap + pre-gist for exactly where you are."""
import os, sys, sqlite3, glob, hashlib

HOME = os.path.expanduser("~")
CACHE = os.path.join(HOME, ".local/share/tess-read")
want = " ".join(sys.argv[1:]).strip().lower()
WINDOW = 3200  # ~1.5 pages each side

dbs = glob.glob(f"{HOME}/Library/Containers/com.apple.iBooksX/Data/Documents/BKLibrary/BKLibrary*.sqlite")
if not dbs:
    print("NO_LIBRARY"); sys.exit(1)
con = sqlite3.connect(f"file:{dbs[0]}?mode=ro", uri=True)
rows = con.execute("""
    SELECT ZTITLE, ZPATH, ZREADINGPROGRESS FROM ZBKLIBRARYASSET
    WHERE ZPATH LIKE '%.epub' AND ZTITLE IS NOT NULL ORDER BY ZLASTOPENDATE DESC
""").fetchall()

book = None
for title, path, prog in rows:
    if want:
        if want in (title or "").lower():
            book = (title, path, prog); break
    else:
        book = (title, path, prog); break
if not book:
    print("NO_BOOK"); sys.exit(1)

title, path, prog = book
key = hashlib.md5((path or "").encode()).hexdigest()[:10]
cache_file = os.path.join(CACHE, f"{key}.md")
if not os.path.exists(cache_file):
    print("NOT_EXTRACTED — run `tess read` first"); sys.exit(1)

text = open(cache_file).read()
pct = (prog or 0)
offset = int(len(text) * pct)
just_read = text[max(0, offset - WINDOW):offset].strip()
coming_up = text[offset:offset + WINDOW].strip()

print(f"[POSITION] {round(pct*100)}% into \"{title}\" (char {offset} of {len(text)})")
print("\n[JUST READ]\n" + (just_read or "(start of book)"))
print("\n[COMING UP]\n" + (coming_up or "(end of book)"))
