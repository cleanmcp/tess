"""Shared vault plumbing for tess's knowledge commands (vault/note/kanban/tasks/base/links).

Everything is plain-file work on the TESS_VAULT markdown vault. Lokus compatibility is
format-exact (see docs/vault.md): .kanban files are written with every field the app's
serde structs require, checkbox states use the app's two-way symbol map, and wiki links
follow the app's [[path|alias#heading^block]] grammar. No Lokus install is ever needed.
"""
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone

VAULT = os.environ.get("TESS_VAULT") or os.path.expanduser("~/Documents/tess-vault")
HUB = os.environ.get("TESS_HUB") or os.path.join(VAULT, "hub")

# folders never scanned: hidden dirs (incl. .lokus/.git/.archive) + dependency junk
SKIP_DIRS = {"node_modules", "__pycache__", "venv", ".venv"}

# keep this wording in sync with _vault_ok in bin/tess — one voice, two languages
GUIDANCE = ("no notes vault yet — the brain features are optional. Point TESS_VAULT at any\n"
            "markdown folder in ~/.config/tess/config (Obsidian/Lokus/plain files all work).")


def die(msg, code=1):
    print(f"tess: {msg}", file=sys.stderr)
    sys.exit(code)


def require_vault():
    if os.path.isdir(VAULT):
        return
    # mirror bash _vault_ok: an EXPLICITLY configured vault self-scaffolds; only the
    # unconfigured default gets the guidance (bin/tess exports TESS_VAULT_CONFIGURED)
    if os.environ.get("TESS_VAULT_CONFIGURED") == "1":
        try:
            os.makedirs(VAULT, exist_ok=True)
            return
        except OSError:
            pass
    print(GUIDANCE)
    sys.exit(1)


def now_iso():
    """RFC3339 UTC with microseconds — same shape chrono's to_rfc3339 writes."""
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return str(uuid.uuid4())


def rel(path):
    p = os.path.abspath(path)
    v = os.path.abspath(VAULT)
    return p[len(v) + 1:] if p.startswith(v + os.sep) else p


def inside_vault(path):
    """Resolve `path` (relative to the vault) and refuse escapes/hidden targets.
    Symlink-hard: the REAL location must sit inside the real vault too, so a
    planted link can't route a write outside or into a dot-folder."""
    full = os.path.abspath(os.path.join(VAULT, path))
    vault_abs = os.path.abspath(VAULT)
    r = rel(full)
    if not full.startswith(vault_abs + os.sep):
        die(f"'{path}' escapes the vault", 2)
    if any(part.startswith(".") for part in r.split(os.sep)):
        die(f"'{path}' is a hidden path — tess never writes into dot-folders", 2)
    # resolve symlinks on the deepest existing ancestor and re-check for real
    probe = full
    while probe and not os.path.exists(probe):
        probe = os.path.dirname(probe)
    real_probe, real_vault = os.path.realpath(probe), os.path.realpath(vault_abs)
    if real_probe != real_vault and not real_probe.startswith(real_vault + os.sep):
        die(f"'{path}' resolves outside the vault (symlink) — refusing", 2)
    rr = real_probe[len(real_vault) + 1:] if real_probe.startswith(real_vault + os.sep) else ""
    if any(part.startswith(".") for part in rr.split(os.sep) if part):
        die(f"'{path}' resolves into a dot-folder (symlink) — refusing", 2)
    return full


def confine_folder(path):
    """A user-supplied vault-relative FOLDER for reads: same confinement as
    inside_vault, plus it must exist and be a directory."""
    full = inside_vault(path)
    if not os.path.isdir(full):
        die(f"no folder '{path}' in the vault (see: tess vault folders)", 2)
    return full


def _skip(name):
    return name.startswith(".") or name in SKIP_DIRS


def walk(root=None, exts=(".md",)):
    """Yield absolute paths under the vault (or `root`), skipping hidden/junk dirs."""
    base = root or VAULT
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not _skip(d))
        for f in sorted(filenames):
            if not exts or f.endswith(tuple(exts)):
                if not f.startswith("."):
                    yield os.path.join(dirpath, f)


def folders(root=None):
    """Relative folder paths inside the vault (skipping hidden/junk), sorted."""
    base = root or VAULT
    out = []
    for dirpath, dirnames, _ in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not _skip(d))
        if dirpath != base:
            out.append(rel(dirpath))
    return out


# ---------------- frontmatter (the regex-lite house parser, slightly grown) --

FM_RE = re.compile(r"^---\n(.*?)\n---\n?", re.S)


def parse_frontmatter(text):
    """(meta, body). Minimal YAML: `key: value`, inline [a, b] arrays, block lists.
    Values stay strings; tags/aliases become lists. Never raises."""
    m = FM_RE.match(text or "")
    if not m:
        return {}, text or ""
    meta, key = {}, None
    for line in m.group(1).splitlines():
        if re.match(r"^\s*-\s+", line) and key:
            if meta.get(key) == "":       # `key:` on its own line opens a block list
                meta[key] = []
            if isinstance(meta.get(key), list):
                meta[key].append(line.split("-", 1)[1].strip().strip("\"'"))
            continue
        km = re.match(r"^([A-Za-z0-9_.-]+):\s*(.*)$", line)
        if not km:
            continue
        key, val = km.group(1), km.group(2).strip()
        if val.startswith("[") and val.endswith("]"):
            meta[key] = [v.strip().strip("\"'") for v in val[1:-1].split(",") if v.strip()]
        elif val == "":
            meta[key] = ""          # may become a block list
        else:
            meta[key] = val.strip("\"'")
    return meta, text[m.end():]


def read_note(path):
    try:
        raw = open(path, errors="ignore").read()
    except OSError:
        return {}, "", ""
    meta, body = parse_frontmatter(raw)
    return meta, body, raw


def make_frontmatter(title, tags=None, description="", extra=None):
    """The vault's own note convention (matches bin/tess _add/_newnote)."""
    lines = ["---", f"title: {title}",
             "tags: [" + ", ".join(tags or []) + "]",
             f"created: {datetime.now().strftime('%Y-%m-%d')}",
             f"description: {description}"]
    for k, v in (extra or {}).items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def note_title(path):
    return os.path.basename(path)[:-3] if path.endswith(".md") else os.path.basename(path)


def resolve_notes(query, limit=20):
    """Note lookup, same ladder as `tess <name>`: exact filename -> partial filename
    -> content match. Returns a list of absolute paths (exact match returns just it).
    A path (abs, or vault-relative with a /) is accepted verbatim — the ambiguity
    listing prints paths, and candidates must always be re-runnable."""
    raw = (query or "").strip()
    if raw and ("/" in raw or raw.endswith(".md")):
        for cand in (raw, raw + ".md",
                     os.path.join(VAULT, raw), os.path.join(VAULT, raw + ".md")):
            if os.path.isfile(cand):
                return [os.path.abspath(cand)]
    q = raw.lower().removesuffix(".md")
    if not q:
        return []
    exact, partial = [], []
    for p in walk():
        name = note_title(p).lower()
        if name == q:
            exact.append(p)
        elif q in name:
            partial.append(p)
    if exact:
        return exact[:limit]
    if partial:
        return partial[:limit]
    hits = []
    for p in walk():
        try:
            if q in open(p, errors="ignore").read().lower():
                hits.append(p)
                if len(hits) >= limit:
                    break
        except OSError:
            pass
    return hits


def atomic_write(path, text):
    """Same-dir dotfile tmp + rename, UTF-8, tmp cleaned up on failure. Writes
    through symlinks (replace the TARGET, never the link — hub.md-style aliases
    must stay aliases). The tmp name must never end in a Lokus-scanned extension
    (.kanban/.base/.md) — the app discovers files by extension while open."""
    if os.path.islink(path):
        path = os.path.realpath(path)
    d, base = os.path.split(path)
    tmp = os.path.join(d, f".{base}.{os.getpid()}.tess-tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------- checkboxes (Lokus's two-way symbol map) --------------------

CHECKBOX = {" ": "todo", "x": "done", "X": "done", "/": "in-progress",
            "!": "urgent", "?": "question", "-": "cancelled", ">": "delegated"}
CHECKBOX_GLYPH = {"todo": "☐", "done": "☑", "in-progress": "◐", "urgent": "‼",
                  "question": "?", "cancelled": "✕", "delegated": "→"}
OPEN_STATES = ("todo", "in-progress", "urgent", "question", "delegated")
TASK_RE = re.compile(r"^(\s*)[-*+] \[([ xX/!?>-])\] (\S.*)$")


def scan_tasks(paths=None):
    """[{file, line (1-based), state, text}] for every checkbox in the vault.
    Checkboxes inside ``` code fences are examples, not tasks — skipped."""
    out = []
    for p in (paths if paths is not None else walk()):
        try:
            fenced = False
            for i, line in enumerate(open(p, errors="ignore"), 1):
                if line.lstrip().startswith("```"):
                    fenced = not fenced
                    continue
                if fenced:
                    continue
                m = TASK_RE.match(line.rstrip("\n"))
                if m:
                    out.append({"file": p, "line": i,
                                "state": CHECKBOX[m.group(2)], "text": m.group(3).strip()})
        except OSError:
            pass
    return out


# ---------------- wiki links -------------------------------------------------

WIKI_RE = re.compile(r"(!?)\[\[([^\[\]]+?)\]\]")


def parse_link(target):
    """'path#heading^block|alias' -> (path, alias). Path may include folders, no .md."""
    body = target.split("|", 1)
    alias = body[1].strip() if len(body) > 1 else None
    path = re.split(r"[#^]", body[0], 1)[0].strip()
    return path.removesuffix(".md"), alias


def extract_links(text):
    """[(path, alias, is_embed)] for every [[...]] outside code fences."""
    out = []
    fenced = False
    for line in (text or "").splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        for m in WIKI_RE.finditer(line):
            path, alias = parse_link(m.group(2))
            if path:
                out.append((path, alias, m.group(1) == "!"))
    return out


def link_targets_index():
    """{lowercased basename -> [abs paths], lowercased rel path (no .md) -> [abs]}."""
    idx = {}
    for p in walk():
        r = rel(p).removesuffix(".md").lower()
        idx.setdefault(os.path.basename(r), []).append(p)
        idx.setdefault(r, []).append(p)
    return idx


def resolve_link(target, idx):
    """Lokus resolution: slash -> path match, else basename match. [] if broken."""
    t = target.lower().removesuffix(".md")
    return idx.get(t if "/" in t else os.path.basename(t), [])


# ---------------- kanban (.kanban JSON, app-schema-exact) --------------------

def col_id(name):
    return name.strip().lower().replace(" ", "-")


def new_card(title, description=None, tags=None, priority="normal", due=None,
             assignee=None, linked_notes=None, checklist=None):
    """Every field the app's serde Card requires — omit none of these."""
    now = now_iso()
    return {"id": new_id(), "title": title, "description": description,
            "tags": tags or [], "assignee": assignee, "priority": priority or "normal",
            "due_date": due, "linked_notes": linked_notes or [], "checklist": checklist or [],
            "created": now, "modified": now}


def new_board(name, columns=("To Do", "In Progress", "Done")):
    now = now_iso()
    return {"version": "1.0.0", "name": name,
            "columns": {col_id(c): {"name": c, "order": i, "cards": []}
                        for i, c in enumerate(columns)},
            "settings": {"card_template": {}, "automations": [], "custom_fields": []},
            "metadata": {"created": now, "modified": now, "created_with": "tess"}}


def kanban_files(root=None):
    return list(walk(root, exts=(".kanban",)))


CARD_REQUIRED = ("id", "title", "tags", "priority", "linked_notes", "checklist",
                 "created", "modified")
_BOARD_MTIME = {}   # path -> mtime_ns at load, for the save-time change check


def _mtime_ns(path):
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def kanban_load(path):
    """Load + hard-validate. A board that fails here is NEVER written back —
    one malformed card makes the whole file unloadable in the app."""
    try:
        data = json.load(open(path))
    except (OSError, ValueError) as e:
        die(f"can't read board {rel(path)}: {e} — fix the file first, tess won't touch it", 2)
    if not isinstance(data.get("columns"), dict):
        die(f"{rel(path)} doesn't look like a kanban board (no columns)", 2)
    _BOARD_MTIME[path] = _mtime_ns(path)
    return data


def kanban_validate(data, path=""):
    """Every card must carry every serde-required field before we write; a
    malformed column is equally unwritable — the app couldn't load it either."""
    for cid, col in data.get("columns", {}).items():
        if not isinstance(col, dict):
            die(f"column '{cid}' in {rel(path)} is malformed — refusing to write "
                f"a board the app can't load", 2)
        for card in col.get("cards") or []:
            missing = [k for k in CARD_REQUIRED if not isinstance(card, dict) or k not in card]
            if missing:
                die(f"card {(card.get('id', '?') if isinstance(card, dict) else '?')[:8]} "
                    f"in {rel(path)}:{cid} is missing {', '.join(missing)} — refusing "
                    f"to write a board the app can't load", 2)


def kanban_save(path, data):
    """Validate-whole-board, then compare-and-swap on mtime_ns: if the file
    changed since load (the Lokus app is open and saved), abort instead of
    clobbering. (A stat→rename window remains; it's documented, not locked.)"""
    kanban_validate(data, path)
    loaded = _BOARD_MTIME.get(path)
    if loaded is not None and _mtime_ns(path) != loaded:
        die(f"{rel(path)} changed on disk since tess read it (Lokus open?) — "
            f"re-run the command", 2)
    data.setdefault("metadata", {})["modified"] = now_iso()
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


DONE_COL_NAMES = {"done", "complete", "completed", "finished", "shipped"}


def find_col(board, name):
    """Column by name/id, case-insensitive via the same transform the app uses."""
    want = col_id(name)
    for cid, col in board.get("columns", {}).items():
        if not isinstance(col, dict):
            continue
        if cid == want or col_id(col.get("name", "")) == want:
            return cid
    return None


def sorted_columns(board):
    """[(col_id, col)] by the integer `order` field (object order is meaningless).
    Tolerant: a malformed column value (null, string) is skipped, never a crash."""
    cols = [(k, v) for k, v in board.get("columns", {}).items() if isinstance(v, dict)]
    return sorted(cols, key=lambda kv: kv[1].get("order", 0))


def board_cards(board):
    """[(col_id, card)] — malformed columns/cards skipped, never a crash."""
    out = []
    for cid, col in board.get("columns", {}).items():
        if not isinstance(col, dict):
            continue
        for card in col.get("cards") or []:
            if isinstance(card, dict):
                out.append((cid, card))
    return out


def find_cards(query, boards=None):
    """Match cards by id prefix or title substring across boards.
    Returns [(path, board, col_id, card)]. A board that fails to parse is
    skipped with a stderr note — one broken file never blocks the others."""
    q = (query or "").strip().lower()
    hits = []
    for path in (boards or kanban_files()):
        try:
            board = json.load(open(path))
        except (OSError, ValueError):
            print(f"tess: skipping unreadable board {rel(path)}", file=sys.stderr)
            continue
        if not isinstance(board.get("columns"), dict):
            continue
        _BOARD_MTIME[path] = _mtime_ns(path)
        for cid, card in board_cards(board):
            if card.get("id", "").lower().startswith(q) or q in (card.get("title") or "").lower():
                hits.append((path, board, cid, card))
    return hits


# ---------------- templates --------------------------------------------------

def template_dirs():
    """Vault-root folders whose name is/ends with 'templates' (e.g. 07-Templates)."""
    out = []
    try:
        for d in sorted(os.listdir(VAULT)):
            full = os.path.join(VAULT, d)
            if os.path.isdir(full) and not _skip(d) and d.lower().rstrip("s").endswith("template"):
                out.append(full)
    except OSError:
        pass
    return out


def find_template(name):
    q = (name or "").lower().removesuffix(".md")
    hits = []
    for d in template_dirs():
        for p in walk(d):
            n = note_title(p).lower()
            if n == q:
                return [p]
            if q in n:
                hits.append(p)
    return hits


VAR_RE = re.compile(r"\{\{\s*([^}|]+?)\s*(?:\|\|\s*\"([^\"]*)\"\s*|\|[^}]*?)?\}\}")


def render_template(text, variables):
    """{{var}} + {{var || "fallback"}}; `{{var | filter}}` uses the var name only
    (filters aren't evaluated). Unknown vars without a fallback stay literal."""
    def sub(m):
        name = m.group(1).strip()
        if name in variables:
            return str(variables[name])
        if m.group(2) is not None:
            return m.group(2)
        return m.group(0)
    return VAR_RE.sub(sub, text or "")


def template_vars(title="", filename=""):
    now = datetime.now()
    return {"date": now.strftime("%Y-%m-%d"), "time": now.strftime("%H:%M"),
            "datetime": now.strftime("%Y-%m-%d %H:%M"), "date.iso": now.date().isoformat(),
            "title": title, "filename": filename, "uuid": new_id(),
            "user": os.environ.get("USER", "")}
