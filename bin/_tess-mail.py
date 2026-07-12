#!/usr/bin/env python3
"""tess mail [query] — email from the local Apple Mail store, with contact names.
Read:    [query] · from <name|addr> · read <id> · search <text>
Actions: send <who> -- <subj> <body> · reply <id> -- <text> · mark <id> read|unread ·
         flag <id> [color|off] · archive <id> · move <id> <mailbox> · delete <id>
Flags: --limit N · --json · --from <addr>. Reads hit the sqlite store directly (never
written); actions go through Mail.app via AppleScript. send/reply/delete always
confirm with a human — non-interactive calls get the exact command to run instead."""
import os, sys, re, glob, json, email, email.policy, sqlite3, subprocess, datetime
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
def get_row(rid, verb="read"):
    try:
        rid = int(rid)
    except (TypeError, ValueError):
        print(f"usage: tess mail {verb} <id>   (ids come from: tess mail)")
        sys.exit(2)
    r = CON.execute(SQL.format(extra="AND m.ROWID = ?").replace("ORDER BY m.date_received DESC", ""),
                    (rid,)).fetchone()
    if not r:
        print(f"no message with id {rid}. (ids come from: tess mail — they refresh after moves)")
        sys.exit(1)
    return mkrow(r)


def cmd_read(rid):
    row = get_row(rid)
    rid = row["id"]
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


# ---------------- actions (AppleScript against Mail.app) ----------------
# The sqlite store is NEVER written — every mutation goes through Mail.app so it
# stays consistent (and syncs to the server). Reads stay on the fast sqlite path.
FLAG_COLORS = {"red": 0, "orange": 1, "yellow": 2, "green": 3, "blue": 4,
               "purple": 5, "gray": 6, "grey": 6}

FIND_BLOCK = '''
    set theAcct to missing value
    repeat with a in accounts
      set eaddrs to (get email addresses of a)
      if eaddrs contains acctAddr then
        set theAcct to a
        exit repeat
      end if
    end repeat
    if theAcct is missing value then return "ERR:no account in Mail.app for " & acctAddr
    -- gmail system boxes (All Mail…) can't be name-addressed at account level, so
    -- work with mailbox OBJECTS throughout; INBOX is searched first.
    set allBoxes to (get mailboxes of theAcct)
    set ordered to {}
    repeat with mb in allBoxes
      if (name of mb) is "INBOX" then
        set beginning of ordered to mb
      else
        set end of ordered to mb
      end if
    end repeat
    set theMsg to missing value
    set foundBox to missing value
    repeat with mb in ordered
      try
        set hits to (messages of mb whose message id is mid)
        if (count of hits) > 0 then
          set theMsg to item 1 of hits
          set foundBox to mb
          exit repeat
        end if
      end try
    end repeat
    if theMsg is missing value then return "ERR:message not found in Mail.app (still syncing? try again)"
'''

ACT_SCRIPT = '''on run argv
  set acctAddr to item 1 of argv
  set mid to item 2 of argv
  set act to item 3 of argv
  set arg1 to item 4 of argv
  tell application "Mail"
''' + FIND_BLOCK + '''
    if act is "mark" then
      set read status of theMsg to (arg1 is "read")
      return "OK:marked " & arg1
    else if act is "flag" then
      if arg1 is "off" then
        set flagged status of theMsg to false
        return "OK:flag removed"
      else
        set flag index of theMsg to (arg1 as integer)
        set flagged status of theMsg to true
        return "OK:flagged"
      end if
    else if act is "delete" then
      delete theMsg
      return "OK:moved to Trash"
    else if act is "move" or act is "archive" then
      set targets to {arg1}
      if act is "archive" then set targets to {"Archive", "All Mail"}
      repeat with nm in targets
        repeat with mb in allBoxes
          if (name of mb) is (nm as string) then
            if (name of foundBox) is (nm as string) then return "OK:already in " & nm
            move theMsg to mb
            return "OK:moved to " & (name of mb)
          end if
        end repeat
      end repeat
      return "ERR:no mailbox named '" & arg1 & "' in " & acctAddr & " (see: tess mail boxes)"
    end if
    return "ERR:unknown action " & act
  end tell
end run'''

SEND_SCRIPT = '''on run argv
  tell application "Mail"
    set outMsg to make new outgoing message with properties ¬
      {subject:(item 2 of argv), content:(item 3 of argv), visible:false}
    tell outMsg
      make new to recipient at end of to recipients with properties {address:(item 1 of argv)}
      set sender to (item 4 of argv)
    end tell
    send outMsg
  end tell
  return "OK:sent"
end run'''

REPLY_SCRIPT = '''on run argv
  set acctAddr to item 1 of argv
  set mid to item 2 of argv
  set replyTxt to item 3 of argv
  set fromAddr to item 4 of argv
  tell application "Mail"
''' + FIND_BLOCK + '''
    set r to reply theMsg without opening window
    set content of r to replyTxt
    if fromAddr is not "" then set sender of r to fromAddr
    send r
    return "OK:replied"
  end tell
end run'''

BOXES_SCRIPT = '''on run argv
  set acctAddr to item 1 of argv
  set out to ""
  tell application "Mail"
    repeat with a in accounts
      set eaddrs to (get email addresses of a)
      set e to item 1 of eaddrs
      if acctAddr is "" or eaddrs contains acctAddr then
        repeat with mb in (mailboxes of a)
          set out to out & e & "\\t" & (name of mb) & "\\n"
        end repeat
      end if
    end repeat
  end tell
  return out
end run'''


def osa(script, *args):
    """Run an AppleScript with argv (injection-safe). -> stdout, or exits with guidance."""
    try:
        p = subprocess.run(["osascript", "-e", script, *args],
                           capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        print("Mail.app didn't respond in 90s — open it once, then retry."); sys.exit(1)
    err = (p.stderr or "").strip()
    if p.returncode != 0 or err:
        if "-1743" in err or "Not authorized" in err:
            print("Mail actions blocked — allow Automation (cmux → Mail):")
            print("  System Settings → Privacy & Security → Automation → cmux → enable Mail.")
        elif "-600" in err or "-10810" in err:
            print("couldn't talk to Mail.app — open Mail once, then retry.")
        else:
            print(f"Mail.app error: {err or 'unknown'}")
        sys.exit(1)
    return (p.stdout or "").strip()


def message_id_of(rid):
    path, _ = find_emlx(rid)
    if not path:
        print(f"[{rid}] has no local message file — can't act on it."); sys.exit(1)
    try:
        mid = (parse_emlx(path).get("Message-ID") or "").strip().strip("<>")
    except Exception:
        mid = ""
    if not mid:
        print(f"[{rid}] has no Message-ID header — can't act on it."); sys.exit(1)
    return mid


def act_result(res, row, action):
    if res.startswith("ERR:"):
        if AS_JSON:
            print(json.dumps({"ok": False, "action": action, "id": row["id"], "error": res[4:]}))
        else:
            print(f"✗ {res[4:]}")
        sys.exit(1)
    detail = res[3:] if res.startswith("OK:") else res
    if AS_JSON:
        print(json.dumps({"ok": True, "action": action, "id": row["id"], "detail": detail}))
    else:
        print(f"✓ {detail} — [{row['id']}] {short(row['subject'], 50)}")
        if action in ("archive", "move", "delete"):
            print(f"{C.grey}  (ids can change after a move — re-run `tess mail` for fresh ones){C.r}")


def confirm_or_die(what, resume_cmd):
    """send/reply/delete are irreversible — a HUMAN must approve, always."""
    if not sys.stdin.isatty():
        print(f"\n{what} needs a human — run it yourself:")
        print(f"  {resume_cmd}")
        sys.exit(2)
    try:
        ans = input(f"{what}? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("cancelled."); sys.exit(0)
    if ans not in ("y", "yes"):
        print("cancelled."); sys.exit(0)


def cmd_simple_action(rid, action, arg=""):
    row = get_row(rid, action)
    mid = message_id_of(row["id"])
    if action == "delete":
        print(f"\n  {C.red}delete{C.r} [{row['id']}] {C.cyan}{row['from_name']}{C.r} — "
              f"{short(row['subject'], 60)}  {C.grey}({row['account']}){C.r}")
        confirm_or_die("delete (→ Trash)", f'tess mail delete {row["id"]}')
    act_result(osa(ACT_SCRIPT, row["account"], mid, action, str(arg)), row, action)


def mail_account_emails():
    """live account emails from Mail.app (newline list, first address per account first)."""
    return [l for l in osa(BOXES_SCRIPT, "").splitlines() if l.strip()]


def pick_sender(explicit):
    """--from substring, else $TESS_MAIL_FROM, else the account holding the most local mail."""
    live = []
    for l in mail_account_emails():
        e = l.split("\t")[0].strip().lower()
        if e and e not in live:
            live.append(e)
    if not explicit:
        cfg = os.environ.get("TESS_MAIL_FROM", "").strip().lower()
        if cfg:
            hits = [e for e in live if cfg in e]
            if len(hits) == 1:
                return hits[0]
    if explicit:
        hits = [e for e in live if explicit.lower() in e]
        if len(hits) == 1:
            return hits[0]
        print(f"--from '{explicit}' matches {len(hits)} accounts:" if hits else
              f"--from '{explicit}' matches no Mail account:")
        for e in live:
            print(f"  - {e}")
        sys.exit(2)
    counts = {}
    for url, tot in CON.execute("SELECT url, total_count FROM mailboxes"):
        _, acct = mbox_info(url)
        e = ACCTS.get(acct, "")
        if e in live:
            counts[e] = counts.get(e, 0) + (tot or 0)
    return max(counts, key=counts.get) if counts else (live[0] if live else None)


def resolve_recipient(q):
    """name/addr -> (display, address); ambiguity: picker on a TTY, guidance otherwise."""
    if "@" in q:
        return q, q.strip()
    ql, cands = q.lower(), {}
    for a, n in contacts_map().items():          # Contacts first…
        if "@" in a and ql in n.lower():
            cands[a.lower()] = (n, a)
    for a, cmt in CON.execute("SELECT DISTINCT address, comment FROM addresses"):  # …then people who've mailed him
        if not a or "@" not in a:
            continue
        disp = cmt or resolve(a)
        if disp and ql in disp.lower() and a.lower() not in cands:
            cands[a.lower()] = (disp if disp != a else a, a)
    out = sorted(cands.values(), key=lambda x: (x[0].lower() != ql, x[0].lower()))
    if not out:
        print(f"no email address found for '{q}' (Contacts + mail history). Use the address itself.")
        sys.exit(1)
    if len(out) == 1:
        return out[0]
    if not sys.stdin.isatty():
        print(f"ambiguous: '{q}' matches multiple addresses:")
        for n, a in out[:8]:
            print(f"  - {n} <{a}>")
        print(f're-run with the exact address, e.g.  tess mail send "{out[0][1]}" -- <subject> <body>')
        sys.exit(2)
    print(f"multiple matches for '{q}':")
    for i, (n, a) in enumerate(out[:8], 1):
        print(f"  {i}. {n}  ({a})")
    pick = input("pick # (Enter to cancel): ").strip()
    if not pick.isdigit() or not (1 <= int(pick) <= min(8, len(out))):
        print("cancelled."); sys.exit(0)
    return out[int(pick) - 1]


def cmd_send(who, subj, body):
    name, addr = resolve_recipient(who)
    sender = pick_sender(FROM_ADDR or None)
    if not sender:
        print("no account found in Mail.app to send from."); sys.exit(1)
    print(f"\n  {C.bold}{C.mag}✉  new mail{C.r}")
    print(f"  {C.grey}from:{C.r} {sender}")
    print(f"  {C.grey}to:{C.r}   {C.cyan}{name}{C.r} {C.grey}<{addr}>{C.r}" if name != addr
          else f"  {C.grey}to:{C.r}   {C.cyan}{addr}{C.r}")
    print(f"  {C.grey}subj:{C.r} {subj}")
    print(f"  {C.grey}{'─' * 50}{C.r}")
    print("\n".join("  " + l for l in body.splitlines()))
    print()
    flagpart = f' --from {sender}' if FROM_ADDR else ""
    confirm_or_die("send", f'tess mail send{flagpart} "{addr}" -- "{subj}" "{body}"')
    res = osa(SEND_SCRIPT, addr, subj, body, sender)
    if AS_JSON:
        print(json.dumps({"ok": res == "OK:sent", "action": "send", "to": addr,
                          "from": sender, "subject": subj}))
    else:
        print(f"✓ sent to {name} <{addr}> from {sender}" if res == "OK:sent" else f"✗ {res}")


def cmd_reply(rid, text):
    row = get_row(rid, "reply")
    mid = message_id_of(row["id"])
    sender = pick_sender(FROM_ADDR) if FROM_ADDR else ""   # default: Mail replies from the thread's account
    print(f"\n  {C.bold}{C.mag}↩  reply{C.r} to [{row['id']}] {C.cyan}{row['from_name']}{C.r} "
          f"{C.grey}<{row['from_addr']}>{C.r}")
    print(f"  {C.grey}subj:{C.r} Re: {row['subject']}")
    print(f"  {C.grey}via:{C.r}  {sender or row['account'] + ' (thread account)'}")
    print(f"  {C.grey}{'─' * 50}{C.r}")
    print("\n".join("  " + l for l in text.splitlines()))
    print()
    confirm_or_die("send reply", f'tess mail reply {row["id"]} -- "{text}"')
    res = osa(REPLY_SCRIPT, row["account"], mid, text, sender)
    if AS_JSON:
        print(json.dumps({"ok": res == "OK:replied", "action": "reply", "id": row["id"],
                          "to": row["from_addr"]}))
    else:
        print(f"✓ replied to {row['from_name']}" if res == "OK:replied" else f"✗ {res}")


def cmd_boxes():
    rows = [l.split("\t") for l in mail_account_emails() if "\t" in l]
    if AS_JSON:
        print(json.dumps([{"account": a, "mailbox": b} for a, b in rows], indent=2))
        return
    print(f"\n  {C.bold}{C.mag}Mail.app mailboxes{C.r}\n")
    last = None
    for a, b in rows:
        if a != last:
            print(f"  {C.cyan}{a}{C.r}"); last = a
        print(f"    {b}")
    print()


# ---------------- args ----------------
# flags live BEFORE `--`; everything after `--` is content (subject/body/reply text)
argv = sys.argv[1:]
post = []
if "--" in argv:
    cut = argv.index("--")
    argv, post = argv[:cut], argv[cut + 1:]

LIMIT, AS_JSON, FROM_ADDR, rest = 25, False, "", []
i = 0
while i < len(argv):
    a = argv[i]
    if a == "--json":
        AS_JSON = True
    elif a == "--from" and i + 1 < len(argv) or a.startswith("--from="):
        FROM_ADDR = a.split("=", 1)[1] if "=" in a else argv[i + 1]
        if "=" not in a:
            i += 1
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
elif sub == "from" and len(rest) > 1:
    cmd_from(" ".join(rest[1:]))
elif sub == "from":
    print("usage: tess mail from <name or address>"); sys.exit(2)
elif sub == "send":
    who = " ".join(rest[1:]).strip()
    if not who or not post:
        print('usage: tess mail send <name|addr> -- "<subject>" "<body>"   [--from <acct>]')
        sys.exit(2)
    cmd_send(who, post[0], " ".join(post[1:]) if len(post) > 1 else "")
elif sub == "reply":
    if len(rest) < 2 or not post:
        print('usage: tess mail reply <id> -- "<text>"'); sys.exit(2)
    cmd_reply(rest[1], " ".join(post))
elif sub == "mark":
    state = rest[2].lower() if len(rest) > 2 else "read"
    if len(rest) < 2 or state not in ("read", "unread"):
        print("usage: tess mail mark <id> read|unread"); sys.exit(2)
    cmd_simple_action(rest[1], "mark", state)
elif sub == "unread":
    if len(rest) < 2:
        print("usage: tess mail unread <id>"); sys.exit(2)
    cmd_simple_action(rest[1], "mark", "unread")
elif sub == "flag":
    color = rest[2].lower() if len(rest) > 2 else "red"
    if len(rest) < 2 or (color != "off" and color not in FLAG_COLORS):
        print(f"usage: tess mail flag <id> [{'|'.join(list(FLAG_COLORS)[:7])}|off]"); sys.exit(2)
    cmd_simple_action(rest[1], "flag", color if color == "off" else FLAG_COLORS[color])
elif sub == "archive":
    if len(rest) < 2:
        print("usage: tess mail archive <id>"); sys.exit(2)
    cmd_simple_action(rest[1], "archive")
elif sub == "move":
    if len(rest) < 3:
        print("usage: tess mail move <id> <mailbox>   (see: tess mail boxes)"); sys.exit(2)
    cmd_simple_action(rest[1], "move", " ".join(rest[2:]))
elif sub == "delete":
    if len(rest) < 2:
        print("usage: tess mail delete <id>"); sys.exit(2)
    cmd_simple_action(rest[1], "delete")
elif sub == "boxes":
    cmd_boxes()
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
