"""Shared helpers for tess python tools: TTY-aware color + Contacts resolution."""
import os, sys, glob, sqlite3, re, json, time

HOME = os.path.expanduser("~")


class _Palette:
    """Colors only when stdout is a real terminal — piped/agent output stays clean."""
    def __init__(self):
        on = sys.stdout.isatty()
        def c(code): return code if on else ""
        self.cyan = c("\033[36m"); self.grey = c("\033[2m"); self.green = c("\033[32m")
        self.yellow = c("\033[33m"); self.mag = c("\033[35m"); self.red = c("\033[31m")
        self.blue = c("\033[34m"); self.bold = c("\033[1m"); self.r = c("\033[0m")

C = _Palette()


def short(t, n):
    t = t or ""
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", r"\1", t)   # [[link|alias]] -> alias
    t = re.sub(r"[*_`=~]{1,2}", "", t)                        # **bold** ==hl== `code`
    t = re.sub(r"^#+\s*", "", t)                              # heading markers
    t = " ".join(t.split())
    return (t[:n - 1] + "…") if len(t) > n else t


# ---------------- Contacts (name from phone / email) ----------------
_CACHE = os.path.join(HOME, ".local/share/tess/contacts.json")
_NAME_SQL = (
    "COALESCE(NULLIF(TRIM(COALESCE(r.ZFIRSTNAME,'')||' '||COALESCE(r.ZLASTNAME,'')),''), "
    "r.ZORGANIZATION, r.ZNICKNAME)"
)


def _norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    return d[-10:] if len(d) >= 10 else d


def contacts_map(max_age=86400):
    try:
        if os.path.exists(_CACHE) and time.time() - os.path.getmtime(_CACHE) < max_age:
            return json.load(open(_CACHE))
    except Exception:
        pass
    m = {}
    for db in glob.glob(f"{HOME}/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb"):
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            for name, phone in con.execute(
                f"SELECT {_NAME_SQL}, p.ZFULLNUMBER FROM ZABCDRECORD r "
                "JOIN ZABCDPHONENUMBER p ON p.ZOWNER=r.Z_PK WHERE p.ZFULLNUMBER IS NOT NULL"):
                k = _norm_phone(phone)
                if k and name and name.strip():
                    m.setdefault(k, name.strip())
            for name, email in con.execute(
                f"SELECT {_NAME_SQL}, e.ZADDRESS FROM ZABCDRECORD r "
                "JOIN ZABCDEMAILADDRESS e ON e.ZOWNER=r.Z_PK WHERE e.ZADDRESS IS NOT NULL"):
                if name and name.strip() and email:
                    m.setdefault(email.lower().strip(), name.strip())
        except Exception:
            pass
    try:
        os.makedirs(os.path.dirname(_CACHE), exist_ok=True)
        json.dump(m, open(_CACHE, "w"))
    except Exception:
        pass
    return m


def find_contacts(query):
    """name (or partial) -> list of (name, number) matches, deduped by name."""
    q = (query or "").strip().lower()
    if not q:
        return []
    seen, out = set(), []
    for db in glob.glob(f"{HOME}/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb"):
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            for name, phone in con.execute(
                f"SELECT {_NAME_SQL}, p.ZFULLNUMBER FROM ZABCDRECORD r "
                "JOIN ZABCDPHONENUMBER p ON p.ZOWNER=r.Z_PK WHERE p.ZFULLNUMBER IS NOT NULL"):
                if name and q in name.lower():
                    key = name.strip().lower()
                    if key not in seen:
                        seen.add(key); out.append((name.strip(), phone))
        except Exception:
            pass
    # exact-name matches first
    out.sort(key=lambda x: (x[0].lower() != q, x[0].lower()))
    return out


def find_number(query):
    """First matching number; if the query is already a number/email, use it."""
    q = (query or "").strip().lower()
    if not q:
        return None
    if "@" in q or (re.sub(r"\D", "", q) and len(re.sub(r"\D", "", q)) >= 7):
        return query.strip()
    c = find_contacts(query)
    return c[0][1] if c else None


def decode_body(data):
    """Extract text from a message.attributedBody typedstream blob."""
    if not data:
        return ""
    try:
        idx = data.index(b"NSString")
    except ValueError:
        return ""
    t = data[idx + 8:]
    t = t[4:] if len(t) > 4 else t
    if not t:
        return ""
    if t[0] == 0x81 and len(t) >= 3:
        ln = int.from_bytes(t[1:3], "little"); s = t[3:3 + ln]
    else:
        ln = t[0]; s = t[1:1 + ln]
    txt = s.decode("utf-8", "ignore")
    if any(mk in txt for mk in ("NSDictionary", "NSNumber", "__kIM", "streamtyped", "NSAttribute", "NSObject")):
        return ""
    return "".join(ch for ch in txt if ch == "\n" or ch >= " ").replace("￼", "").strip()


def chat_labels(con):
    """chat.db connection -> {chat_id: label}. Groups get a name or participant list;
    1:1 chats get the contact name."""
    parts = {}
    try:
        for cid, hid in con.execute(
            "SELECT chj.chat_id, h.id FROM chat_handle_join chj JOIN handle h ON h.ROWID=chj.handle_id"):
            parts.setdefault(cid, []).append(resolve(hid))
    except Exception:
        pass
    labels = {}
    try:
        for cid, style, dn, ident in con.execute(
            "SELECT ROWID, style, display_name, chat_identifier FROM chat"):
            if dn and dn.strip():
                labels[cid] = ("👥 " if style == 43 else "") + dn.strip()
            elif style != 43:
                labels[cid] = resolve(ident) if ident else "unknown"
            else:
                ps = parts.get(cid, [])
                labels[cid] = "👥 " + (", ".join(ps[:3]) + ("…" if len(ps) > 3 else "") if ps else "group")
    except Exception:
        pass
    return labels


_MAP = None


def resolve(handle):
    """phone/email -> contact name if known, else the handle unchanged."""
    global _MAP
    if _MAP is None:
        _MAP = contacts_map()
    if not handle:
        return handle
    h = str(handle).strip()
    if "@" in h:
        return _MAP.get(h.lower(), h)
    return _MAP.get(_norm_phone(h), h)
