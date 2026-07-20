#!/usr/bin/env python3
"""tess read [title] — launch Claude as a reading companion for your current Apple Book."""
import os, sys, sqlite3, zipfile, re, glob, html, hashlib

HOME = os.path.expanduser("~")
CACHE = os.path.join(HOME, ".local/share/tess-read")
os.makedirs(CACHE, exist_ok=True)
want = " ".join(sys.argv[1:]).strip().lower()

def die(msg):
    print(msg); sys.exit(1)

dbs = glob.glob(f"{HOME}/Library/Containers/com.apple.iBooksX/Data/Documents/BKLibrary/BKLibrary*.sqlite")
if not dbs:
    die("can't find your Apple Books library (grant Full Disk Access to your terminal app).")
con = sqlite3.connect(f"file:{dbs[0]}?mode=ro", uri=True)
try:
    rows = con.execute("""
        SELECT ZTITLE, ZAUTHOR, ZPATH, ZREADINGPROGRESS
        FROM ZBKLIBRARYASSET
        WHERE ZPATH LIKE '%.epub' AND ZTITLE IS NOT NULL
        ORDER BY ZLASTOPENDATE DESC
    """).fetchall()
except Exception:
    die("can't read the library — grant your terminal app Full Disk Access, then restart it.")

book = None
for title, author, path, prog in rows:
    if want:
        if want in (title or "").lower():
            book = (title, author, path, prog); break
    else:
        book = (title, author, path, prog); break   # most recently opened epub
if not book:
    print("no matching book. Your epubs:")
    for title, *_ in rows[:10]:
        print("  •", title)
    sys.exit(1)

title, author, path, prog = book
if not path or not os.path.exists(path):
    die(f"'{title}' file not found locally (open it once in Apple Books to download it).")

def epub_to_text(p):
    # Apple Books stores epubs as either a .epub zip OR an unzipped directory.
    if os.path.isdir(p):
        def read(name):
            with open(os.path.join(p, *name.split("/")), "rb") as fh:
                return fh.read()
        def names():
            out = []
            for root, _, fs in os.walk(p):
                for f in fs:
                    out.append(os.path.relpath(os.path.join(root, f), p).replace(os.sep, "/"))
            return out
    else:
        z = zipfile.ZipFile(p)
        read = z.read
        names = z.namelist
    files = []
    try:
        container = read("META-INF/container.xml").decode("utf-8", "ignore")
        opf_path = re.search(r'full-path="([^"]+)"', container).group(1)
        opf = read(opf_path).decode("utf-8", "ignore")
        base = os.path.dirname(opf_path)
        manifest = {}
        for it in re.findall(r"<item\b[^>]*>", opf):
            i = re.search(r'id="([^"]+)"', it); h = re.search(r'href="([^"]+)"', it)
            if i and h:
                manifest[i.group(1)] = h.group(1)
        for ref in re.findall(r'idref="([^"]+)"', opf):
            if ref in manifest:
                fp = manifest[ref]
                files.append(os.path.join(base, fp) if base else fp)
    except Exception:
        files = [n for n in names() if n.lower().endswith((".xhtml", ".html", ".htm"))]
    out = []
    for f in files:
        try:
            raw = read(f).decode("utf-8", "ignore")
        except Exception:
            continue
        raw = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
        txt = html.unescape(re.sub(r"<[^>]+>", " ", raw))
        txt = re.sub(r"[ \t]+", " ", txt)
        txt = re.sub(r"\n\s*\n\s*\n+", "\n\n", txt).strip()
        if txt:
            out.append(txt)
    return "\n\n".join(out)

key = hashlib.md5(path.encode()).hexdigest()[:10]
cache_file = os.path.join(CACHE, f"{key}.md")
if not os.path.exists(cache_file):
    print(f"  extracting “{title}”…")
    try:
        text = epub_to_text(path)
    except Exception as e:
        die(f"couldn't read the epub: {e}")
    if len(text) < 200:
        die("extracted almost no text — the book may be a cloud placeholder; open it in Apple Books once.")
    open(cache_file, "w").write(f"# {title}\nby {author}\n\n{text}")

pct = round((prog or 0) * 100)
clean = re.sub(r'[<>:"/\\|?*]', "", (title or "book").split("/")[0]).strip()[:70].strip()
vault = os.environ.get("TESS_VAULT", os.path.expanduser("~/Documents/tess-vault"))
book_note = os.path.join(vault, "Books", f"{clean}.md")
_home = os.environ.get("TESS_HOME") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
mode = None
for _m in (os.path.expanduser("~/.config/tess/modes/read.md"),
           os.path.join(_home, "modes", "read.md"),
           os.path.expanduser("~/.claude/modes/read.md")):
    if os.path.exists(_m):
        mode = open(_m).read()
        break
if mode is None:
    die("reading-companion mode file missing (modes/read.md)")
mode += (f"\n\n---\n**Current book:** {title} — {author}. Full text: `{cache_file}`. "
         f"**Reading-notes file for this book:** `{book_note}` (read it at start; append their lessons/observations per chapter there). "
         f"Apple Books has been opened to their spot. FIRST THING: run `tess readpos` and give them "
         f"the 📍/⏪/⏩ (where you are · recap · coming-up gist), then offer to explain anything.")

# open Apple Books to their current book/position so they read natively there
os.system("open -a Books >/dev/null 2>&1")
print(f"  📖 {title} — {pct}% in  (opened in Apple Books)\n")
os.execvp("claude", ["claude", "--add-dir", CACHE, "--append-system-prompt", mode])
