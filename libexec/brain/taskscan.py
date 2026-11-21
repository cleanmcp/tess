#!/usr/bin/env python3
"""tess tasks … · tess reminders — checkbox scanning + check-off over the vault.

  tasks [scope] [--all] [--json]         open tasks (scope = vault folder or note name)
  tasks done <match…> [--in <scope>]     check off exactly one open task
  reminders-compat [--json]              legacy `tess reminders` face — never exits nonzero
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_vault import (CHECKBOX, CHECKBOX_GLYPH, GUIDANCE, OPEN_STATES, TASK_RE,  # noqa: E402
                        VAULT, atomic_write, die, inside_vault, note_title, rel,
                        require_vault, resolve_notes, scan_tasks, walk)
from tess_common import C, short  # noqa: E402

# same checkbox char class as tess_vault.TASK_RE — replaces ONLY the state char
BOX_RE = re.compile(r"^(\s*[-*+] \[)[ xX/!?>-]\]")

STATE_COLOR = {"in-progress": C.yellow, "urgent": C.red, "done": C.grey, "cancelled": C.grey}
STATE_ORDER = ("urgent", "in-progress", "todo", "question", "delegated", "done", "cancelled")


def rows_json(rows):
    return [{"file": rel(r["file"]), "line": r["line"], "state": r["state"],
             "text": r["text"]} for r in rows]


def resolve_scope(query, as_json):
    """Scope = a vault folder first, then a note (exact rel path, then the resolve_notes
    ladder). Returns a list of abs paths, or None meaning the whole vault."""
    q = (query or "").strip()
    if not q:
        return None
    full = inside_vault(q)                       # dies 2 on escapes / dot-paths
    if os.path.isdir(full):
        return list(walk(full))
    for cand in (full, full + ".md"):            # exact rel path — re-runnable from exit-3 output
        if os.path.isfile(cand):
            return [cand]
    hits = resolve_notes(q)
    if not hits:
        die(f"no folder or note matching '{q}' (folders: tess vault folders)", 2)
    if len(hits) > 1:
        if as_json:
            print(json.dumps([{"path": rel(p), "title": note_title(p)} for p in hits], indent=2))
        else:
            for p in hits:
                print(rel(p))
        sys.exit(3)
    return hits


def cmd_tasks(args):
    as_json = "--json" in args
    show_all = "--all" in args
    scope = " ".join(a for a in args if not a.startswith("-")).strip()
    rows = scan_tasks(resolve_scope(scope, as_json))
    open_rows = [r for r in rows if r["state"] in OPEN_STATES]
    shown = rows if show_all else open_rows
    if as_json:
        print(json.dumps(rows_json(shown), indent=2))
        return
    extra = f" · {len(rows)} total" if show_all else ""
    where = f" · {scope}" if scope else ""
    print(f"\n  {C.bold}{C.mag}tasks{C.r}  {C.grey}({len(open_rows)} open{extra}{where}){C.r}\n")
    if not shown:
        hidden = len(rows) - len(open_rows)
        hint = (f"nothing open — {hidden} finished (see them: tess tasks --all)" if hidden
                else "no tasks yet — any '- [ ] …' checkbox line in a note counts")
        print(f"  {C.grey}{hint}{C.r}\n")
        return
    by_file = {}
    for r in shown:
        by_file.setdefault(r["file"], []).append(r)
    for f, rs in by_file.items():
        print(f"  {C.grey}{rel(f)}{C.r}")
        for r in rs:
            col = STATE_COLOR.get(r["state"], "")
            glyph = CHECKBOX_GLYPH.get(r["state"], "☐")
            print(f"    {col}{glyph} {short(r['text'], 76)}{C.r if col else ''}")
        print()
    counts = {s: sum(1 for r in shown if r["state"] == s) for s in STATE_ORDER}
    tally = " · ".join(f"{n} {s}" for s, n in counts.items() if n)
    print(f"  {C.grey}{tally}   (check one off: tess tasks done <text>){C.r}\n")


def cmd_done(args):
    as_json = "--json" in args
    scope_q = None
    if "--in" in args:
        i = args.index("--in")
        if i + 1 >= len(args):
            die("--in needs a note or folder", 2)
        scope_q = args[i + 1]
        del args[i:i + 2]
    match = " ".join(a for a in args if not a.startswith("-")).strip()
    if not match:
        die("usage: tess tasks done <match…> [--in <note|folder>]", 2)
    paths = resolve_scope(scope_q, as_json) if scope_q else None
    q = match.lower()
    hits = [r for r in scan_tasks(paths)
            if r["state"] in OPEN_STATES and q in r["text"].lower()]
    if not hits:
        die(f"no open task matching '{match}' (list them: tess tasks)", 2)
    if len(hits) > 1:
        if as_json:
            print(json.dumps(rows_json(hits), indent=2))
        else:
            for r in hits:
                print(f"{rel(r['file'])}:{r['line']}  {r['text']}")
        sys.exit(3)
    hit = hits[0]
    path, line_no = hit["file"], hit["line"]
    try:
        # Re-read with the SAME line scheme scan_tasks numbered by: file ITERATION
        # (splits on newlines only). splitlines() also splits on \x0b/\x0c/  etc,
        # which shifts line numbers and would flip the wrong line — never use it here.
        # newline="" keeps each line's original ending; errors="ignore" matches the
        # scan's decode so the text comparison below lines up.
        with open(path, encoding="utf-8", errors="ignore", newline="") as f:
            lines = list(f)
        with open(path, "rb") as f:
            original = f.read()
    except OSError as e:
        die(f"can't edit {rel(path)}: {e}", 2)
    # byte-for-byte guard: if the lossy decode dropped anything (invalid utf-8), a
    # rewrite would silently corrupt the file — refuse instead
    if "".join(lines).encode("utf-8") != original:
        die(f"{rel(path)} isn't clean utf-8 — rewriting would drop bytes; fix it by hand", 2)
    target = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
    m = TASK_RE.match(target.rstrip("\r\n"))
    # never re-search at write time: same line number must still hold the same open task
    if not m or m.group(3).strip() != hit["text"] or CHECKBOX.get(m.group(2)) != hit["state"]:
        die(f"{rel(path)}:{line_no} changed since the scan — re-run", 2)
    # replace ONLY the checkbox state char in that one element
    lines[line_no - 1] = BOX_RE.sub(r"\g<1>x]", target, count=1)
    atomic_write(path, "".join(lines))
    print(f"✓ done: {hit['text']}  ({rel(path)}:{line_no})")


def cmd_reminders(args):
    """Legacy `tess reminders` — the voice router runs this; it must never fail."""
    try:
        if not os.path.isdir(VAULT):
            print(GUIDANCE)
            return
        rows = [r for r in scan_tasks() if r["state"] in OPEN_STATES]
        if "--json" in args:
            print(json.dumps(rows_json(rows), indent=2))
            return
        print(f"\n  {C.bold}{C.mag}open reminders / follow-ups{C.r}  {C.grey}({len(rows)} total){C.r}\n")
        if not rows:
            print(f"  {C.green}nothing open — all clear{C.r}\n")
            return
        for r in rows[:30]:
            print(f"  {C.yellow}☐{C.r} {short(r['text'], 66):<66} {C.grey}{note_title(r['file'])}{C.r}")
        if len(rows) > 30:
            print(f"\n  {C.grey}…and {len(rows) - 30} more. Open a source note with  tess <name>{C.r}")
        print()
    except Exception:
        pass                                     # a broken vault must not break the router


def main():
    args = sys.argv[1:]
    if args and args[0] == "reminders-compat":
        cmd_reminders(args[1:])
        return
    require_vault()
    if args and args[0] == "done":
        cmd_done(args[1:])
    else:
        cmd_tasks(args)


if __name__ == "__main__":
    main()
