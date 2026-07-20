#!/usr/bin/env python3
"""tess people | companies | reminders — roster/index from the Lokus vault."""
import os, sys, glob, re

VAULT = os.environ.get("TESS_VAULT", os.path.expanduser("~/Documents/tess-vault"))
cat = sys.argv[1] if len(sys.argv) > 1 else "people"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_common import C, short  # noqa: E402

PEOPLE_TAGS = {"person", "profile", "contact"}          # individual-person markers
COMPANY_TAGS = {"company", "companies", "org", "startup", "vendor", "account"}
EXCLUDE_TAGS = {"content", "daily", "index", "meta", "template", "tasks", "prompts"}
INDEX_NAME_HINTS = ("prospect", "connection", "outreach", "-list", "-notes", "playbook", "queue")

def parse(path):
    try:
        txt = open(path, errors="ignore").read()
    except Exception:
        return None
    title = tags = desc = None
    tags = []
    body = txt
    m = re.match(r"^---\n(.*?)\n---", txt, re.S)
    if m:
        body = txt[m.end():]
        for line in m.group(1).splitlines():
            if line.startswith("title:"):
                title = line.split(":", 1)[1].strip().strip('"')
            elif line.startswith("tags:"):
                tags = [t.lower() for t in re.findall(r"[A-Za-z0-9_-]+", line.split(":", 1)[1])]
            elif line.startswith("description:"):
                desc = line.split(":", 1)[1].strip()
    if not title:
        title = os.path.basename(path)[:-3]
    if not desc:
        for l in body.splitlines():
            s = l.strip()
            if s and not s.startswith(("#", ">", "-", "|", "---")):
                desc = s
                break
    return title, tags, (desc or "")


files = [f for f in glob.glob(VAULT + "/**/*.md", recursive=True) if "/." not in f.replace(VAULT, "")]

if cat == "reminders":
    rows = []
    for f in files:
        try:
            for line in open(f, errors="ignore"):
                if re.match(r"\s*-\s*\[ \]\s+\S", line):
                    task = re.sub(r"\s*-\s*\[ \]\s*", "", line).strip()
                    rows.append((task, os.path.basename(f)[:-3]))
        except Exception:
            pass
    print(f"\n  {C.bold}{C.mag}open reminders / follow-ups{C.r}  {C.grey}({len(rows)} total){C.r}\n")
    if not rows:
        print(f"  {C.green}nothing open — all clear{C.r}\n"); sys.exit(0)
    for task, src in rows[:30]:
        print(f"  {C.yellow}☐{C.r} {short(task,66):<66} {C.grey}{src}{C.r}")
    if len(rows) > 30:
        print(f"\n  {C.grey}…and {len(rows) - 30} more. Open a source note with  tess <name>{C.r}")
    print()
    sys.exit(0)

want = PEOPLE_TAGS if cat == "people" else COMPANY_TAGS
folder_hit = ("/06-network/", "/people/") if cat == "people" else ("/companies/", "/accounts/")
items = []
for f in files:
    p = parse(f)
    if not p:
        continue
    title, tags, desc = p
    fl = f.lower()
    base = os.path.basename(fl)
    if set(tags) & EXCLUDE_TAGS:                 # skip content/index/template notes
        continue
    if any(h in base for h in INDEX_NAME_HINTS): # skip list/roster docs, keep individuals
        continue
    if (set(tags) & want) or any(h in fl for h in folder_hit):
        items.append((title, desc, f))

items = sorted({(t, d, f) for t, d, f in items})
label = "people" if cat == "people" else "companies"
print(f"\n  {C.bold}{C.mag}{label}{C.r}  {C.grey}({len(items)}) — open one with  tess <name>{C.r}\n")
if not items:
    hint = "add someone: tess add \"<name>\" -- <note>  (tag it #person)" if cat == "people" \
           else "no companies yet — tag a note #company and it shows here"
    print(f"  {C.grey}{hint}{C.r}\n"); sys.exit(0)
for title, desc, f in items:
    print(f"  {C.cyan}{short(title,26):<26}{C.r} {C.grey}{short(desc,58)}{C.r}")
print()
