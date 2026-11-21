#!/usr/bin/env python3
"""tess bases · tess base <name> · tess base query — run Lokus .base queries on the vault.

.base files live in <vault>/.lokus/bases/ and are YAML written by the Lokus app. tess
reads them with a strict mini-YAML reader covering only that machine-written subset —
anything fancier (anchors, aliases, multiline scalars, flow mappings) dies with guidance
instead of guessing at semantics.
"""
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_vault import (VAULT, confine_folder, die, note_title, read_note, rel,  # noqa: E402
                        require_vault, walk)
from tess_common import C, short  # noqa: E402

BASES_DIR = os.path.join(VAULT, ".lokus", "bases")
CANT = "this .base uses YAML tess can't parse — simplify it or open it in Lokus"
NO_BASES_HINT = "no bases yet — Lokus creates them in .lokus/bases (ad-hoc: tess base query)"
OPS = ("==", "!=", ">=", "<=", ">", "<", "contains", "starts-with", "ends-with",
       "is-empty", "is-not-empty")


# ---------------- mini-YAML (machine-written .base subset only) --------------

class Unsupported(Exception):
    pass


def _strip_comment(line):
    """Drop a trailing comment, YAML-style: a # starts a comment only OUTSIDE
    quotes and at line start / after whitespace. A quote only OPENS at a token
    boundary (start, whitespace, ':', '[', ','), so an apostrophe inside a word
    (it's) never flips quote state and hide/keep the wrong half of the line."""
    out, q = [], None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'" and (i == 0 or line[i - 1] in " \t:[,"):
            q = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _lines(text):
    toks = []
    for n, raw in enumerate((text or "").splitlines(), 1):
        line = _strip_comment(raw.expandtabs(2))
        if not line.strip() or line.strip() in ("---", "..."):
            continue
        toks.append([len(line) - len(line.lstrip(" ")), line.strip(), n])
    return toks


def _flow_seq(s, ln):
    if not s.endswith("]"):
        raise Unsupported(f"line {ln}: unterminated flow sequence")
    items, cur, q = [], "", None
    for ch in s[1:-1]:
        if q:
            cur += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q, cur = ch, cur + ch
        elif ch in "[{":
            raise Unsupported(f"line {ln}: nested flow collections")
        elif ch == ",":
            items.append(cur.strip())
            cur = ""
        else:
            cur += ch
    items.append(cur.strip())
    return [_scalar(x, ln) for x in items if x]


def _scalar(s, ln):
    s = s.strip()
    if s[:1] in ("&", "*") or s.startswith("<<"):
        raise Unsupported(f"line {ln}: anchors/aliases")
    if re.match(r"^[|>][+-]?\d*$", s):
        raise Unsupported(f"line {ln}: multiline scalars")
    if s.startswith("{"):
        raise Unsupported(f"line {ln}: flow mappings")
    if s.startswith("["):
        return _flow_seq(s, ln)
    if s[:1] in ("\"", "'"):
        if len(s) >= 2 and s.endswith(s[0]):
            return s[1:-1]
        raise Unsupported(f"line {ln}: unterminated quote")
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~"):
        return None
    for cast in (int, float):
        try:
            return cast(s)
        except ValueError:
            pass
    return s


def _parse(toks, i, indent):
    if toks[i][1] == "-" or toks[i][1].startswith("- "):
        return _parse_seq(toks, i, indent)
    return _parse_map(toks, i, indent)


def _parse_map(toks, i, indent):
    out = {}
    while i < len(toks) and toks[i][0] == indent and not (toks[i][1] == "-" or toks[i][1].startswith("- ")):
        _, text, ln = toks[i]
        m = re.match(r"^([^:\s][^:]*?)\s*:(?:\s+(.*))?$", text)
        if not m:
            raise Unsupported(f"line {ln}: not a 'key: value' line")
        key = m.group(1).strip("\"'")
        val = (m.group(2) or "").strip()
        if val:
            out[key] = _scalar(val, ln)
            i += 1
        elif i + 1 < len(toks) and (toks[i + 1][0] > indent or
                                    (toks[i + 1][0] == indent and toks[i + 1][1].startswith("- "))):
            out[key], i = _parse(toks, i + 1, toks[i + 1][0])
        else:
            out[key] = None
            i += 1
    return out, i


def _parse_seq(toks, i, indent):
    out = []
    while i < len(toks) and toks[i][0] == indent and (toks[i][1] == "-" or toks[i][1].startswith("- ")):
        ind, text, ln = toks[i]
        rest = text[1:].strip()
        if not rest:
            if i + 1 < len(toks) and toks[i + 1][0] > indent:
                v, i = _parse(toks, i + 1, toks[i + 1][0])
                out.append(v)
            else:
                out.append(None)
                i += 1
        elif re.match(r"^[^:\s][^:]*?:(?:\s|$)", rest):
            toks[i] = [ind + (len(text) - len(rest)), rest, ln]
            v, i = _parse_map(toks, i, toks[i][0])
            out.append(v)
        else:
            out.append(_scalar(rest, ln))
            i += 1
    return out, i


def yaml_load(text):
    """Parse the .base subset. Raises Unsupported on anything beyond it."""
    toks = _lines(text)
    if not toks:
        return {}
    val, i = _parse(toks, 0, toks[0][0])
    if i < len(toks):
        raise Unsupported(f"line {toks[i][2]}: unexpected indentation")
    return val


# ---------------- base files -------------------------------------------------

def base_files():
    try:
        return [os.path.join(BASES_DIR, f) for f in sorted(os.listdir(BASES_DIR))
                if f.endswith(".base") and not f.startswith(".")]
    except OSError:
        return []


def try_load(path):
    """(definition, error). Parse failures come back as text, never a traceback."""
    try:
        raw = open(path, errors="ignore").read()
    except OSError as e:
        return None, str(e)
    try:
        bdef = yaml_load(raw)
    except Unsupported as e:
        return None, str(e)
    return (bdef if isinstance(bdef, dict) else {}), None


def base_views(bdef):
    """Views as an ordered list of dicts — Lokus writes either a list or a name->view
    mapping (settings.defaultView first when it does)."""
    v = bdef.get("views")
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    if isinstance(v, dict):
        items = [(k, dict({"name": k}, **view)) for k, view in v.items() if isinstance(view, dict)]
        dv = (bdef.get("settings") or {}).get("defaultView") if isinstance(bdef.get("settings"), dict) else None
        items.sort(key=lambda kv: kv[0] != dv)
        return [view for _, view in items]
    return []


def view_filters(view):
    """(filter list, AND|OR). Filters may be a bare list or {condition, filters/rules}."""
    f = view.get("filters")
    cond = view.get("condition") or "AND"
    if isinstance(f, dict):
        cond = f.get("condition") or f.get("conjunction") or cond
        f = f.get("filters") or f.get("rules") or []
    return ([x for x in f if isinstance(x, dict)] if isinstance(f, list) else []), str(cond).upper()


def view_cols(view):
    cols = view.get("columns")
    if not cols and isinstance(view.get("display"), dict):
        cols = view["display"].get("columns")
    out = []
    for c in cols if isinstance(cols, list) else []:
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, dict) and c.get("visible") is not False and c.get("property"):
            out.append(str(c["property"]))
    return out or ["name", "modified"]


# ---------------- rows -------------------------------------------------------

def _iso(ts):
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def note_row(path):
    """One queryable row per note. Frontmatter WINS for every key it defines
    (a note's own created/modified/etc are the truth); file stats only fill
    the gaps — name/path/size and the stat dates when the note doesn't say."""
    meta, _, _ = read_note(path)
    try:
        st = os.stat(path)
    except OSError:
        return None
    row = dict(meta)
    row["title"] = str(meta.get("title") or "").strip() or note_title(path)
    row.setdefault("name", note_title(path))
    row.setdefault("path", rel(path))
    row.setdefault("size", st.st_size)
    row.setdefault("created", _iso(getattr(st, "st_birthtime", None) or st.st_ctime))
    row.setdefault("modified", _iso(st.st_mtime))
    return row


def note_tags(meta):
    t = meta.get("tags")
    if isinstance(t, list):
        return [str(x).strip("#").lower() for x in t]
    if isinstance(t, str) and t.strip():
        return [x.strip("#").lower() for x in re.findall(r"[^,\s]+", t)]
    return []


def match(row, key, op, want):
    """One filter op against one row. Missing property = empty. Lists (tags) match by
    membership; numbers compare numerically when both sides parse; ISO dates lexically."""
    v = row.get(key)
    empty = v is None or v == "" or v == [] or (isinstance(v, str) and not v.strip())
    if op == "is-empty":
        return empty
    if op == "is-not-empty":
        return not empty
    if v is None:
        v = ""
    if isinstance(v, list):
        vl = [str(x).lower() for x in v]
        w = str(want).lower()
        if op == "contains":
            return any(w == x or w in x for x in vl)
        if op == "==":
            return w in vl
        if op == "!=":
            return w not in vl
        v = ", ".join(str(x) for x in v)
    s, w = str(v), str(want)
    if op in (">", ">=", "<", "<=") and not s.strip():
        return False          # ordering against a missing value never matches
    if op == "contains":
        return w.lower() in s.lower()
    if op == "starts-with":
        return s.lower().startswith(w.lower())
    if op == "ends-with":
        return s.lower().endswith(w.lower())
    try:
        a, b = float(s), float(w)
    except ValueError:
        a, b = s.lower(), w.lower()
    return {"==": a == b, "!=": a != b, ">": a > b, ">=": a >= b,
            "<": a < b, "<=": a <= b}[op]


def compile_view_filter(f, label):
    key = f.get("property") or f.get("field") or f.get("key")
    op = str(f.get("op") or f.get("operator") or "==")
    want = f.get("value", "")
    if not key:
        die(f"{label}: a filter has no property (edit the .base in Lokus)", 2)
    if op not in OPS:
        die(f"{label}: filter op '{op}' not supported (supported: {' '.join(OPS)})", 2)
    return lambda r: match(r, str(key), op, want)


def _missing(v):
    return v is None or v == "" or v == []


def _sort_key(v):
    s = ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
    try:
        return (0, float(s), "")
    except ValueError:
        return (1, 0.0, s.lower())


def apply_sort(rows, spec):
    """spec: list of {property, direction} (or 'key:desc' strings). Stable multi-key;
    rows missing the key always sort last, whatever the direction."""
    if isinstance(spec, (dict, str)):
        spec = [spec]
    for item in reversed(spec if isinstance(spec, list) else []):
        if isinstance(item, str):
            key, _, d = item.partition(":")
            desc = d.lower() == "desc"
        elif isinstance(item, dict):
            key = item.get("property") or item.get("key") or ""
            desc = str(item.get("direction") or "asc").lower() == "desc"
        else:
            continue
        if key:
            have = [r for r in rows if not _missing(r.get(key))]
            rest = [r for r in rows if _missing(r.get(key))]
            have.sort(key=lambda r: _sort_key(r.get(key)), reverse=desc)
            rows = have + rest
    return rows


# ---------------- output -----------------------------------------------------

def _cell(v, key=""):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    s = str(v)
    if key in ("created", "modified") and re.match(r"^\d{4}-\d{2}-\d{2}T", s):
        return s[:10]
    return s


def print_table(rows, cols):
    data = [[short(_cell(r.get(c), c), 40) for c in cols] for r in rows]
    widths = [max([len(c)] + [len(d[i]) for d in data]) for i, c in enumerate(cols)]
    print("  " + "  ".join(f"{C.grey}{c:<{w}}{C.r}" for c, w in zip(cols, widths)).rstrip())
    for d in data:
        print("  " + "  ".join(f"{x:<{w}}" for x, w in zip(d, widths)).rstrip())


def print_rows(title, subtitle, rows, cols, as_json, empty_hint):
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    sub = f" — {subtitle}" if subtitle else ""
    print(f"\n  {C.bold}{C.mag}{title}{C.r}  {C.grey}({len(rows)}){sub}{C.r}\n")
    if not rows:
        print(f"  {C.grey}{empty_hint}{C.r}\n")
        return
    print_table(rows, cols)
    print()


# ---------------- commands ---------------------------------------------------

def source_summary(src):
    if not isinstance(src, dict):
        return "?"
    t = str(src.get("type") or "folder").lower()
    if t == "folder":
        return f"folder:{src.get('path') or '/'}"
    if t == "tag":
        return f"tag:{src.get('tag') or src.get('path') or src.get('value') or '?'}"
    return t


def cmd_bases(args):
    as_json = "--json" in args
    out = []
    for p in base_files():
        stem = os.path.basename(p)[:-5]
        bdef, err = try_load(p)
        if err:
            out.append({"name": stem, "path": rel(p), "error": "unparseable"})
            continue
        views = base_views(bdef)
        out.append({"name": str(bdef.get("name") or stem), "path": rel(p),
                    "source": source_summary(bdef.get("source")),
                    "views": len(views),
                    "filters": sum(len(view_filters(v)[0]) for v in views)})
    if as_json:
        print(json.dumps(out, indent=2))
        return
    print(f"\n  {C.bold}{C.mag}bases{C.r}  {C.grey}({len(out)}) — run one with  tess base <name>{C.r}\n")
    if not out:
        print(f"  {C.grey}{NO_BASES_HINT}{C.r}\n")
        return
    for b in out:
        if b.get("error"):
            print(f"  {C.cyan}{short(b['name'], 22):<22}{C.r} {C.grey}can't parse — open it in Lokus{C.r}")
        else:
            print(f"  {C.cyan}{short(b['name'], 22):<22}{C.r} {short(b['source'], 28):<28} "
                  f"{C.grey}{b['views']} views · {b['filters']} filters{C.r}")
    print()


def resolve_base(q, as_json):
    files = base_files()
    if not files:
        die(f"no base named '{q}' — {NO_BASES_HINT}", 2)
    cands = []
    for p in files:
        stem = os.path.basename(p)[:-5]
        bdef, err = try_load(p)
        cands.append((p, stem, str((bdef or {}).get("name") or stem), bdef, err))
    # a path-looking query (contains / — the exact form the ambiguity listing
    # prints) is THE answer: candidates must re-run verbatim
    if "/" in q:
        for c in cands:
            if rel(c[0]).lower() in (q, q + ".base"):
                return c
    # an exact filename stem is unique in one directory — also verbatim, and it
    # beats another base whose display NAME happens to collide with it
    stem_exact = [c for c in cands if c[1].lower() == q]
    if len(stem_exact) == 1:
        return stem_exact[0]
    exact = [c for c in cands if q in (c[1].lower(), c[2].lower())]
    hits = exact or [c for c in cands if q in c[1].lower() or q in c[2].lower()]
    if not hits:
        die(f"no base named '{q}' (see: tess bases)", 2)
    if len(hits) > 1:
        if as_json:
            print(json.dumps([{"name": c[1], "path": rel(c[0])} for c in hits], indent=2))
        else:
            for c in hits:
                print(f"{c[1]}  {rel(c[0])}")
        sys.exit(3)
    return hits[0]


def source_rows(path, bdef):
    src = bdef.get("source") if isinstance(bdef.get("source"), dict) else {}
    stype = str(src.get("type") or "folder").lower()
    if stype == "folder":
        sub = str(src.get("path") or "").strip("/")
        # confine_folder is symlink-hard and prefix-safe ('/x/v' vs '/x/v2');
        # ''/'.' mean the whole vault
        root = os.path.abspath(VAULT) if sub in ("", ".") else confine_folder(sub)
        rec = src.get("recursive")
        if rec is None:
            rec = True
        files = walk(root) if rec else \
            (os.path.join(root, f) for f in sorted(os.listdir(root))
             if f.endswith(".md") and not f.startswith("."))
        return [r for r in (note_row(f) for f in files) if r]
    if stype == "tag":
        tag = str(src.get("tag") or src.get("path") or src.get("value") or "").strip("#").lower()
        if not tag:
            die(f"{rel(path)}: tag source has no tag (edit the .base in Lokus)", 2)
        out = []
        for f in walk():
            meta, _, _ = read_note(f)
            if tag in note_tags(meta):
                r = note_row(f)
                if r:
                    out.append(r)
        return out
    die(f"{rel(path)}: source type '{stype}' not supported yet (folder and tag work)", 2)


def cmd_show(args):
    as_json = "--json" in args
    q = " ".join(a for a in args if not a.startswith("-")).strip().lower().removesuffix(".base")
    path, stem, name, bdef, err = resolve_base(q, as_json)
    if err:
        die(f"{rel(path)}: {err} — {CANT}", 2)
    rows = source_rows(path, bdef)
    views = base_views(bdef)
    view = views[0] if views else {}
    filters, cond = view_filters(view)
    preds = [compile_view_filter(f, rel(path)) for f in filters]
    if preds:
        keep = any if cond == "OR" else all
        rows = [r for r in rows if keep(p(r) for p in preds)]
    rows = apply_sort(rows, view.get("sort") or [{"property": "modified", "direction": "desc"}])
    print_rows(name or stem, str(view.get("name") or "") or None, rows, view_cols(view),
               as_json, "no notes match — widen the view in Lokus or try: tess base query")


WHERE_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*(==|!=|>=|<=|=|>|<)\s*(.*)$")


def compile_where(expr):
    e = (expr or "").strip()
    m = re.match(r"^([A-Za-z0-9_.-]+)\s+(is-empty|is-not-empty)$", e)
    if m:
        key, op, want = m.group(1), m.group(2), ""
    else:
        m = WHERE_RE.match(e)
        if not m:
            die(f"bad where '{expr}' — use key<op>value (= contains · == != > >= < <=) "
                f"or 'key is-empty' / 'key is-not-empty'", 2)
        key, op, want = m.groups()
        want = want.strip().strip("\"'")
        if op == "=":
            op = "contains"
    if key.lower() in ("tag", "tags"):
        key = "tags"          # list membership via the list branch of match()
    return lambda r: match(r, key, op, want)


def cmd_query(args):
    as_json, frm, wheres, sort_spec, cols, limit = False, None, [], None, None, None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--json":
            as_json = True
        elif a in ("--from", "--where", "--sort", "--cols", "--limit"):
            if i + 1 >= len(args):
                die(f"{a} needs a value", 2)
            v = args[i + 1]
            i += 1
            if a == "--from":
                frm = v
            elif a == "--where":
                wheres.append(v)
            elif a == "--sort":
                sort_spec = v
            elif a == "--cols":
                cols = [c.strip() for c in v.split(",") if c.strip()]
            else:
                try:
                    limit = int(v)
                except ValueError:
                    die("--limit needs a number", 2)
        else:
            die(f"unknown arg '{a}' — usage: tess base query [--from <folder>] "
                f"[--where \"<expr>\"] [--sort k[:desc]] [--cols a,b] [--limit N] [--json]", 2)
        i += 1
    root = VAULT
    if frm:
        sub = frm.strip("/")
        # confine_folder is symlink-hard and prefix-safe ('/x/v' vs '/x/v2');
        # ''/'.' mean the whole vault
        root = os.path.abspath(VAULT) if sub in ("", ".") else confine_folder(sub)
    preds = [compile_where(w) for w in wheres]
    rows = [r for r in (note_row(p) for p in walk(root)) if r]
    rows = [r for r in rows if all(p(r) for p in preds)]
    rows = apply_sort(rows, [sort_spec] if sort_spec else [{"property": "modified", "direction": "desc"}])
    if limit is not None:
        rows = rows[:max(limit, 0)]
    print_rows("base query", frm, rows, cols or ["name", "modified"], as_json,
               "no notes match — drop a --where or check keys with: tess base query --json")


def main():
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "bases"
    if cmd == "bases":
        require_vault()
        cmd_bases(argv[1:])
    elif cmd == "base":
        require_vault()
        rest = argv[1:]
        if rest and rest[0] == "query":
            cmd_query(rest[1:])
        elif [a for a in rest if not a.startswith("-")]:
            cmd_show(rest)
        else:
            die("usage: tess base <name> [--json] · tess base query [--from <folder>] "
                "[--where \"<expr>\"] [--sort k[:desc]] [--cols a,b] [--limit N] [--json] "
                "(list: tess bases)", 2)
    else:
        die(f"unknown subcommand '{cmd}' (use: tess bases · tess base <name> · tess base query)", 2)


if __name__ == "__main__":
    main()
