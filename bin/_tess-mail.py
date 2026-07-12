#!/usr/bin/env python3
"""tess mail [query] — recent email from the local Apple Mail store, with contact names.
Subcommands: from <name|addr> · read <id> · search <text>. Flags: --limit N · --json.
Read-only (never marks read, never sends). Needs Full Disk Access."""
import os, sys, re, glob, json, email, email.policy, sqlite3, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tess_common import C, resolve, short, contacts_map  # noqa: E402

HOME = os.path.expanduser("~")
MAILROOT = f"{HOME}/Library/Mail"
# mailboxes hidden from the default list (a query or `search` still reaches them)
HIDDEN = {"spam", "junk", "trash", "deleted messages", "drafts", "sendlater"}
BODY_SCAN_CAP = 2000  # newest bodies scanned by `search` (whole store, on this size)


def die_perm():
    print("can't read Mail — grant Full Disk Access to cmux, then restart cmux.")
    print("  System Settings → Privacy & Security → Full Disk Access → enable cmux.")
    sys.exit(1)


def die_nostore():
    print("no local mail store found — Apple Mail isn't set up on this Mac.")
    sys.exit(1)


def store():
    """-> (mail root dir, Envelope Index path) for the newest V* store."""
    try:
        vs = [d for d in os.listdir(MAILROOT) if re.fullmatch(r"V\d+", d)]
    except PermissionError:
        die_perm()
    except FileNotFoundError:
        die_nostore()
    if not vs:
        die_nostore()
    v = max(vs, key=lambda d: int(d[1:]))
    db = f"{MAILROOT}/{v}/MailData/Envelope Index"
    if not os.path.exists(db):
        die_nostore()
    return f"{MAILROOT}/{v}", db


ROOT, DB = store()
try:
    CON = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    CON.execute("SELECT 1 FROM messages LIMIT 1")
except Exception:
    die_perm()


# ---------------- accounts / mailboxes ----------------
def account_emails():
    """account UUID -> its email address, peeked from message headers (no cache).
    Delivered-To/X-Original-To only exist on RECEIVED mail and name the account
    itself; To: (a draft's recipient!) is a last resort, INBOX scanned first."""
    out = {}
    for d in glob.glob(f"{ROOT}/*/"):
        u = os.path.basename(d.rstrip("/"))
        if not re.fullmatch(r"[0-9A-F-]{36}", u):
            continue
        fallback = None
        files = glob.glob(f"{d}INBOX.mbox/**/Messages/*.emlx", recursive=True) or \
            glob.glob(f"{d}**/Messages/*.emlx", recursive=True)
        for f in files[:20]:
            try:
                raw = open(f, "rb").read(4096).decode("utf-8", "ignore")
            except Exception:
                continue
            m = re.search(r"^(?:Delivered-To|X-Original-To):.*?([\w.+-]+@[\w.-]+)", raw, re.M | re.I)
            if m:
                out[u] = m.group(1).lower()
                break
            m = re.search(r"^To:.*?([\w.+-]+@[\w.-]+)", raw, re.M | re.I)
            if m and not fallback:
                fallback = m.group(1).lower()
        out.setdefault(u, fallback or u[:8].lower())
    return out


ACCTS = account_emails()
MULTI = len(ACCTS) > 1


def acct_short(u):
    m = re.search(r"@([^.]+)", ACCTS.get(u, ""))
    return m.group(1) if m else (ACCTS.get(u) or u or "?")[:8]


from urllib.parse import unquote  # noqa: E402


def mbox_info(url):
    """mailbox url -> (display name, account uuid)."""
    if not url:
        return "?", ""
    m = re.match(r"\w+://([0-9A-Fa-f-]{36})/(.*)", url)
    acct, path = (m.group(1), unquote(m.group(2))) if m else ("", unquote(url))
    name = path.replace("[Gmail]/", "").strip("/").lower()
    if name.startswith("sent"):
        name = "sent"
    return name or "?", acct


# gmail keeps one row per message (in All Mail) — the `labels` table says which
# messages are ALSO in INBOX, so we can show/filter the real inbox membership.
def inbox_ids():
    try:
        return {r[0] for r in CON.execute(
            "SELECT l.message_id FROM labels l JOIN mailboxes mb ON mb.ROWID=l.mailbox_id "
            "WHERE mb.url LIKE '%/INBOX'")}
    except Exception:
        return set()


INBOX = inbox_ids()


# ---------------- rows ----------------
SQL = """
    SELECT m.ROWID, m.date_received, a.address, a.comment, s.subject, su.summary,
           m.read, mb.url
    FROM messages m
    LEFT JOIN addresses a ON a.ROWID = m.sender
    LEFT JOIN subjects s ON s.ROWID = m.subject
    LEFT JOIN summaries su ON su.ROWID = m.summary
    LEFT JOIN mailboxes mb ON mb.ROWID = m.mailbox
    WHERE m.deleted = 0 {extra}
    ORDER BY m.date_received DESC
"""


def mkrow(r):
    rid, ts, addr, cmt, subj, snip, read, url = r
    mb, acct = mbox_info(url)
    if rid in INBOX and mb == "all mail":
        mb = "inbox"
    name = resolve(addr) if addr else None
    if (not name or name == addr) and cmt:
        name = cmt
    me = (addr or "").lower() == ACCTS.get(acct, "")
    return {"id": rid, "ts": ts, "from_name": name or addr or "?", "from_addr": addr or "",
            "subject": subj or "(no subject)", "snippet": (snip or "").strip(),
            "unread": read == 0, "from_me": me, "mailbox": mb, "account": ACCTS.get(acct, "")}


def when(ts):
    try:
        dt = datetime.datetime.fromtimestamp(ts)
        fmt = "%b %d %H:%M" if dt.year == datetime.datetime.now().year else "%b %d %Y"
        return dt.strftime(fmt)
    except Exception:
        return "?"


def show_list(rows, title):
    if AS_JSON:
        for r in rows:
            r["date"] = datetime.datetime.fromtimestamp(r["ts"]).isoformat() if r["ts"] else None
            del r["ts"]
        print(json.dumps(rows, indent=2))
        return
    print(f"\n  {C.bold}{C.mag}{title}{C.r}\n")
    for r in rows:
        mark = f"{C.yellow}●{C.r}" if r["unread"] else (
            f"{C.green}→{C.r}" if r["from_me"] else f"{C.grey}·{C.r}")
        tag = "" if r["mailbox"] in ("inbox", "all mail") else r["mailbox"]
        if MULTI:
            tag = f"{tag} @{acct_short_by_email(r['account'])}".strip()
        tail = f" {C.grey}— {short(r['snippet'], 34)}{C.r}" if r["snippet"] else ""
        tag = f"  {C.grey}{tag}{C.r}" if tag else ""
        print(f"  {C.grey}{when(r['ts']):>12}{C.r} {mark} {C.cyan}{short(r['from_name'], 20):<20}{C.r}"
              f" [{r['id']}] {short(r['subject'], 46)}{tail}{tag}")
    if not rows:
        print(f"  {C.grey}no mail found.{C.r}")
    print()


def acct_short_by_email(e):
    m = re.search(r"@([^.]+)", e or "")
    return m.group(1) if m else (e or "?")[:8]


def fetch(filt, include_hidden=False, need=None):
    out = []
    for r in CON.execute(SQL.format(extra="")):
        row = mkrow(r)
        if not include_hidden and row["mailbox"] in HIDDEN:
            continue
        if filt and not filt(row):
            continue
        out.append(row)
        if len(out) >= (need or LIMIT):
            break
    return out


# ---------------- emlx (full bodies) ----------------
def find_emlx(rid):
    for pat in (f"{ROOT}/**/Messages/{rid}.emlx", f"{ROOT}/**/Messages/{rid}.partial.emlx"):
        for f in glob.iglob(pat, recursive=True):
            return f, f.endswith(".partial.emlx")
    return None, False


def parse_emlx(path):
    raw = open(path, "rb").read()
    nl = raw.index(b"\n")
    n = int(raw[:nl].split()[0])
    return email.message_from_bytes(raw[nl + 1:nl + 1 + n], policy=email.policy.default)


def html_to_text(h):
    h = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", h)
    h = re.sub(r"(?i)<(br|/p|/div|/tr|/li|/h[1-6])[^>]*>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    import html as _h
    h = _h.unescape(h)
    h = "\n".join(" ".join(l.split()) for l in h.splitlines())
    return re.sub(r"\n{3,}", "\n\n", h).strip()


def part_text(p):
    try:
        return p.get_content()
    except Exception:
        payload = p.get_payload(decode=True) or b""
        return payload.decode(p.get_content_charset() or "utf-8", "ignore")


def body_of(msg):
    plain = htm = None
    for p in msg.walk():
        if p.get_content_maintype() != "text" or p.get_filename():
            continue
        ct = p.get_content_type()
        if ct == "text/plain" and plain is None:
            plain = part_text(p)
        elif ct == "text/html" and htm is None:
            htm = part_text(p)
    if plain and plain.strip():
        return plain.strip()
    if htm:
        return html_to_text(htm)
    return ""


# ---------------- commands ----------------
def cmd_read(rid):
    try:
        rid = int(rid)
    except (TypeError, ValueError):
        print("usage: tess mail read <id>   (ids come from: tess mail)")
        sys.exit(2)
    r = CON.execute(SQL.format(extra="AND m.ROWID = ?").replace("ORDER BY m.date_received DESC", ""),
                    (rid,)).fetchone()
    if not r:
        print(f"no message with id {rid}. (ids come from: tess mail)")
        sys.exit(1)
    row = mkrow(r)
    path, partial = find_emlx(rid)
    body, atts, to, cc = "", [], "", ""
    if path:
        try:
            msg = parse_emlx(path)
            body = body_of(msg)
            atts = [f for f in (p.get_filename() for p in msg.walk()) if f]
            to, cc = str(msg.get("To", "")), str(msg.get("Cc", ""))
        except Exception as e:
            body = f"(couldn't parse message file: {e})"
    else:
        body = "(body not downloaded locally — open Mail.app to fetch it)"
    if AS_JSON:
        print(json.dumps({**{k: v for k, v in row.items() if k != "ts"},
                          "date": datetime.datetime.fromtimestamp(row["ts"]).isoformat() if row["ts"] else None,
                          "to": to, "cc": cc, "body": body, "attachments": atts,
                          "partial": partial}, indent=2))
        return
    print(f"\n  {C.bold}{C.mag}✉  {row['subject']}{C.r}")
    print(f"  {C.grey}from:{C.r} {C.cyan}{row['from_name']}{C.r} {C.grey}<{row['from_addr']}>{C.r}")
    if to:
        print(f"  {C.grey}to:{C.r}   {short(to, 90)}")
    if cc:
        print(f"  {C.grey}cc:{C.r}   {short(cc, 90)}")
    flags = " · ".join(x for x in [row["mailbox"], row["account"],
                                   "unread" if row["unread"] else "",
                                   "partial download" if partial else ""] if x)
    print(f"  {C.grey}{when(row['ts'])} · {flags}{C.r}")
    print(f"  {C.grey}{'─' * 60}{C.r}")
    print("\n".join("  " + l for l in (body or "(empty)").splitlines()))
    for a in atts:
        print(f"  {C.blue}📎 {a}{C.r}")
    print()


def cmd_search(text):
    ql = text.lower()
    hits = {}
    for r in CON.execute(SQL.format(extra="")):
        row = mkrow(r)
        if row["mailbox"] in ("trash", "deleted messages"):
            continue
        hay = " ".join([row["from_name"], row["from_addr"], row["subject"], row["snippet"]]).lower()
        if ql in hay:
            row["match"] = "header"
            hits[row["id"]] = row
    # body pass: newest first, whole store up to the cap
    files = []
    for f in glob.iglob(f"{ROOT}/**/Messages/*.emlx", recursive=True):
        m = re.match(r"(\d+)(\.partial)?\.emlx$", os.path.basename(f))
        if m:
            files.append((int(m.group(1)), f))
    files.sort(reverse=True)
    scanned, capped = 0, False
    for rid, f in files:
        if rid in hits:
            continue
        if scanned >= BODY_SCAN_CAP:
            capped = True
            break
        scanned += 1
        try:
            body = body_of(parse_emlx(f))
        except Exception:
            continue
        i = body.lower().find(ql)
        if i < 0:
            continue
        r = CON.execute(SQL.format(extra="AND m.ROWID = ?").replace("ORDER BY m.date_received DESC", ""),
                        (rid,)).fetchone()
        if not r:
            continue
        row = mkrow(r)
        ctx = " ".join(body[max(0, i - 30):i + len(ql) + 40].split())
        row["match"] = "body"
        row["snippet"] = f"…{ctx}…"
        hits[rid] = row
    rows = sorted(hits.values(), key=lambda r: r["ts"] or 0, reverse=True)[:LIMIT]
    show_list(rows, f"mail · search '{text}'")
    if capped and not AS_JSON:
        print(f"  {C.grey}(bodies: searched the newest {BODY_SCAN_CAP} only){C.r}\n")


def cmd_from(who):
    ql = who.lower()
    # a contact NAME also matches all of that person's addresses from Contacts
    known = {a for a, n in contacts_map().items() if "@" in a and ql in n.lower()}

    def f(row):
        return (ql in row["from_name"].lower() or ql in row["from_addr"].lower()
                or row["from_addr"].lower() in known)
    show_list(fetch(f, include_hidden=True), f"mail · from {who}")


# ---------------- args ----------------
LIMIT, AS_JSON, rest = 25, False, []
argv = sys.argv[1:]
i = 0
while i < len(argv):
    a = argv[i]
    if a == "--json":
        AS_JSON = True
    elif a == "--limit" and i + 1 < len(argv) or a.startswith("--limit="):
        v = a.split("=", 1)[1] if "=" in a else argv[i + 1]
        if "=" not in a:
            i += 1
        try:
            LIMIT = max(1, int(v))
        except ValueError:
            print(f"bad --limit '{v}' — pass a number, e.g. --limit 10"); sys.exit(2)
    else:
        rest.append(a)
    i += 1

sub = rest[0].lower() if rest else ""
if sub == "read":
    cmd_read(rest[1] if len(rest) > 1 else None)
elif sub == "search":
    if len(rest) < 2:
        print("usage: tess mail search <text>"); sys.exit(2)
    cmd_search(" ".join(rest[1:]))
elif sub == "from":
    if len(rest) < 2:
        print("usage: tess mail from <name or address>"); sys.exit(2)
    cmd_from(" ".join(rest[1:]))
else:
    q = " ".join(rest).strip()
    ql = q.lower()

    def f(row):
        if not ql:
            return True
        return (ql in row["from_name"].lower() or ql in row["from_addr"].lower()
                or ql in row["subject"].lower() or ql in row["snippet"].lower()
                or ql == row["mailbox"])
    show_list(fetch(f, include_hidden=bool(ql)), f"mail · {q}" if q else "recent mail")
