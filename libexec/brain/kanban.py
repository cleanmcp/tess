#!/usr/bin/env python3
"""tess kanban — Lokus-compatible .kanban boards in the vault.

Subcommands (argv[1]; anything else is treated as a board name):
  (bare) [board] [--json]        render a board / list all boards
  new <name> [--in <folder>]     create a board (To Do / In Progress / Done)
  add [board] <title> [--col c] [--desc d] [--due YYYY-MM-DD]
      [--priority p] [--tags a,b] [--note <wiki target>]
  move <card> <col> [--board b]  move a card (id prefix or title substring)
  done <card> [--board b]        move a card to the done-ish column
  rm <card> [--board b]          delete a card

Exit codes: 0 ok · 1 unconfigured vault · 2 usage/not-found · 3 ambiguous
(candidates one per line on stdout; with --json a JSON array).
"""
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_vault import (DONE_COL_NAMES, col_id, confine_folder, die, find_cards,   # noqa: E402
                        find_col, inside_vault, kanban_files, kanban_load,
                        kanban_save, new_board, new_card, now_iso, rel,
                        require_vault, sorted_columns)
from tess_common import C, short  # noqa: E402

PRIORITIES = {"low", "normal", "medium", "high", "urgent"}
PRI_MARK = ("high", "urgent")
DONE_CAP = 10


# ---------------- small plumbing --------------------------------------------

def flagval(args, name):
    """Pop `--flag value` out of args; None when absent."""
    if name not in args:
        return None
    i = args.index(name)
    if i + 1 >= len(args):
        die(f"{name} needs a value", 2)
    v = args[i + 1]
    del args[i:i + 2]
    return v


def _stem(path):
    return os.path.basename(path)[:-len(".kanban")]


def _peek(path):
    """Tolerant board read for listing/matching — a broken file never kills a scan."""
    try:
        d = json.load(open(path))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _bname(board, path):
    return board.get("name") or _stem(path)


def _is_done(cid, col):
    return cid in DONE_COL_NAMES or col_id(col.get("name") or "") in DONE_COL_NAMES


def _col_names(board):
    return ", ".join(c for c, _ in sorted_columns(board)) or "(none)"


def _cards(col):
    """Card list of a column, malformed-tolerant: non-list `cards` -> [],
    non-dict entries skipped — mirrors the lib's board_cards leniency."""
    v = col.get("cards")
    return [c for c in v if isinstance(c, dict)] if isinstance(v, list) else []


# ---------------- board / card resolution -----------------------------------

def resolve_board(query, as_json=False):
    """Board by filename stem or board name, ci substring; exact beats partial.
    Ambiguous -> exit 3, rel paths (or JSON candidate objects) on stdout."""
    files = kanban_files()
    if not files:
        die("no boards yet (create one: tess kanban new <name>)", 2)
    if not query:
        if len(files) == 1:
            return files[0]
        die("several boards — say which: " + ", ".join(_stem(p) for p in files), 2)
    raw = query.strip().lower()
    q = raw.removesuffix(".kanban")
    # a path-looking query (contains / or ends .kanban — the exact form the
    # ambiguity listing prints) is THE answer: candidates re-run verbatim
    if "/" in raw or raw.endswith(".kanban"):
        for p in files:
            if rel(p).lower() in (raw, q + ".kanban"):
                return p
    exact, partial = [], []
    for p in files:
        s = _stem(p).lower()
        n = ((_peek(p) or {}).get("name") or "").strip().lower()
        if q in (s, n):
            exact.append(p)
        elif q in s or (n and q in n):
            partial.append(p)
    hits = exact or partial
    if not hits:
        die(f"no board named '{query}' (see: tess kanban)", 2)
    if len(hits) > 1:
        if as_json:
            print(json.dumps([{"path": rel(p),
                               "name": (_peek(p) or {}).get("name") or _stem(p)}
                              for p in hits], indent=2))
        else:
            for p in hits:
                print(rel(p))
        sys.exit(3)
    return hits[0]


def resolve_card(query, board_flag):
    """One card by id prefix / title substring; scoped to --board when given.
    0 -> die 2 · >1 -> exit 3 with `<id8>  <title> (<board>:<col>)` lines."""
    q = (query or "").strip()
    if not q:
        die("which card? give an id prefix or title substring", 2)
    scope = [resolve_board(board_flag)] if board_flag else None
    hits = find_cards(q, boards=scope)
    if not hits:
        die(f"no card matching '{query}' (see the board: tess kanban)", 2)
    if len(hits) > 1:
        for path, board, cid, card in hits:
            print(f"{(card.get('id') or '')[:8]}  {card.get('title') or ''} "
                  f"({_bname(board, path)}:{cid})")
        sys.exit(3)
    return hits[0]


# ---------------- rendering --------------------------------------------------

def _card_bits(card, width):
    """(plain, colored) one-line card fitted to `width` visible chars."""
    id8 = (card.get("id") or "")[:8]
    pri = (card.get("priority") or "").lower() in PRI_MARK
    due = str(card.get("due_date") or "")[:10]
    for use_due in ((True, False) if due else (False,)):
        tail = f" ({id8})" + (" !" if pri else "") + (f" {due}" if due and use_due else "")
        if width - len(tail) - 2 >= 8 or not use_due:
            break
    title = short(card.get("title") or "(untitled)", max(6, width - len(tail) - 2))
    plain = f"• {title}{tail}"
    colored = (f"• {title} {C.grey}({id8}){C.r}"
               + (f" {C.red}!{C.r}" if pri else "")
               + (f" {C.grey}{due}{C.r}" if due and use_due else ""))
    return plain, colored


def _col_cells(cid, col, width):
    """[(plain, colored)] card rows for one column (done-ish: dim + capped)."""
    done = _is_done(cid, col)
    cards = _cards(col)
    cells = []
    for card in (cards[:DONE_CAP] if done else cards):
        plain, colored = _card_bits(card, width)
        cells.append((plain, f"{C.grey}{plain}{C.r}" if done else colored))
    if done and len(cards) > DONE_CAP:
        more = f"… {len(cards) - DONE_CAP} more"
        cells.append((more, f"{C.grey}{more}{C.r}"))
    if not cards:
        cells.append(("(empty)", f"{C.grey}(empty){C.r}"))
    return cells


def _render_side_by_side(cols, colw):
    heads, bodies = [], []
    for cid, col in cols:
        done = _is_done(cid, col)
        head = f"{col.get('name') or cid} ({len(_cards(col))})"[:colw]
        heads.append((head, done))
        bodies.append(_col_cells(cid, col, colw))
    line = "  "
    for head, done in heads:
        style = C.grey if done else C.bold
        line += f"{style}{head}{C.r}" + " " * (colw - len(head)) + "  "
    print(line.rstrip())
    print("  " + "  ".join(f"{C.grey}{'─' * colw}{C.r}" for _ in heads))
    for r in range(max(len(b) for b in bodies)):
        line = "  "
        for cells in bodies:
            if r < len(cells):
                plain, colored = cells[r]
                line += colored + " " * max(0, colw - len(plain)) + "  "
            else:
                line += " " * (colw + 2)
        print(line.rstrip())


def _render_stacked(cols):
    for cid, col in cols:
        style = C.grey if _is_done(cid, col) else C.bold
        print(f"  {style}{col.get('name') or cid}{C.r}  "
              f"{C.grey}({len(_cards(col))}){C.r}")
        for _, colored in _col_cells(cid, col, 74):
            print(f"    {colored}")
        print()


def render_board(path, board):
    cols = sorted_columns(board)
    total = sum(len(_cards(c)) for _, c in cols)
    print(f"\n  {C.bold}{C.mag}{_bname(board, path)}{C.r}  "
          f"{C.grey}({total} cards · {rel(path)}){C.r}\n")
    if not cols:
        print(f"  {C.grey}no columns — open the board in Lokus to add some{C.r}\n")
        return
    if sys.stdout.isatty():
        width = shutil.get_terminal_size().columns
        colw = min(34, (width - 2 - 2 * len(cols)) // len(cols))
        if colw >= 22:
            _render_side_by_side(cols, colw)
            print()
            return
    _render_stacked(cols)


def list_boards(files, as_json):
    rows = []
    for p in files:
        d = _peek(p)
        if d is None or not isinstance(d.get("columns"), dict):
            rows.append({"name": _stem(p), "path": rel(p), "columns": {},
                         "cards": 0, "modified": None, "unreadable": True})
            continue
        counts = {cid: len(_cards(c)) for cid, c in sorted_columns(d)}
        mod = ((d.get("metadata") or {}).get("modified") or "")[:10]
        if not mod:
            try:
                from datetime import date
                mod = date.fromtimestamp(os.stat(p).st_mtime).isoformat()
            except OSError:
                mod = None
        rows.append({"name": d.get("name") or _stem(p), "path": rel(p),
                     "columns": counts, "cards": sum(counts.values()), "modified": mod})
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    print(f"\n  {C.bold}{C.mag}kanban boards{C.r}  "
          f"{C.grey}({len(rows)}) — render one: tess kanban <name>{C.r}\n")
    for r in rows:
        if r.get("unreadable"):
            print(f"  {C.grey}{short(r['name'], 20):<20} "
                  f"{r['path']:<28} (can't parse — not a kanban board){C.r}")
            continue
        counts = " · ".join(f"{cid}:{n}" for cid, n in r["columns"].items()) or "no columns"
        print(f"  {C.cyan}{short(r['name'], 20):<20}{C.r} {C.grey}{r['path']:<28}{C.r} "
              f"{counts}" + (f"  {C.grey}{r['modified']}{C.r}" if r["modified"] else ""))
    print()


# ---------------- subcommands ------------------------------------------------

def cmd_bare(args):
    as_json = "--json" in args
    if as_json:
        args.remove("--json")
    board_flag = flagval(args, "--board")
    pos = [a for a in args if not a.startswith("-")]
    if len(pos) > 1:
        die("usage: tess kanban [board] [--json]", 2)
    query = board_flag or (pos[0] if pos else None)
    files = kanban_files()
    if not files:
        if as_json:
            print("[]")
            return
        print(f"\n  {C.grey}no kanban boards yet — create one: tess kanban new <name>{C.r}\n")
        return
    if not query and len(files) > 1:
        list_boards(files, as_json)
        return
    path = resolve_board(query, as_json)
    board = kanban_load(path)
    if as_json:
        print(json.dumps(board, indent=2))
        return
    render_board(path, board)


def cmd_new(args):
    in_dir = flagval(args, "--in")
    pos = [a for a in args if not a.startswith("-")]
    if not pos:
        die("usage: tess kanban new <name> [--in <folder>]", 2)
    name = " ".join(pos).strip()
    if not name or not re.fullmatch(r"[A-Za-z0-9 ._-]+", name):
        die(f"bad board name '{name or ' '.join(pos)}' — allowed characters: "
            f"letters digits space . _ -", 2)
    if name.startswith("."):
        die(f"bad board name '{name}' — a leading dot would hide the file", 2)
    if in_dir:
        confine_folder(in_dir)
    path = inside_vault(os.path.join(in_dir, f"{name}.kanban") if in_dir
                        else f"{name}.kanban")
    if os.path.exists(path):
        die(f"{rel(path)} already exists (render it: tess kanban \"{name}\")", 2)
    kanban_save(path, new_board(name))
    print(f"created {rel(path)}")


def cmd_add(args):
    col_q = flagval(args, "--col")
    desc = flagval(args, "--desc")
    due = flagval(args, "--due")
    pri = flagval(args, "--priority")
    tags = flagval(args, "--tags")
    note = flagval(args, "--note")
    board_flag = flagval(args, "--board")
    pos = [a for a in args if not a.startswith("-")]
    if board_flag and len(pos) == 1:
        board_q, title = board_flag, pos[0]
    elif not board_flag and len(pos) == 2:
        board_q, title = pos
    elif not board_flag and len(pos) == 1:
        board_q, title = None, pos[0]
    else:
        die('usage: tess kanban add [board] "<title>" [--col c] [--desc d] '
            '[--due YYYY-MM-DD] [--priority p] [--tags a,b] [--note <target>]', 2)
    if due and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
        die(f"--due wants YYYY-MM-DD (got '{due}')", 2)
    pri = (pri or "normal").lower()
    if pri not in PRIORITIES:
        die(f"--priority must be one of: {', '.join(sorted(PRIORITIES))}", 2)
    path = resolve_board(board_q)
    board = kanban_load(path)
    cols = sorted_columns(board)
    if not cols:
        die(f"{rel(path)} has no columns — open it in Lokus first", 2)
    if col_q:
        cid = find_col(board, col_q)
        if cid is None:
            die(f"no column '{col_q}' in {_bname(board, path)} "
                f"(columns: {_col_names(board)})", 2)
    else:
        cid = cols[0][0]
    card = new_card(title, description=desc,
                    tags=[t.strip() for t in (tags or "").split(",") if t.strip()],
                    priority=pri, due=due, linked_notes=[note] if note else None)
    board["columns"][cid].setdefault("cards", []).append(card)
    kanban_save(path, board)
    print(f"added {card['id'][:8]} to {_bname(board, path)}:{cid}")


def _move(path, board, src, card, dest):
    board["columns"][src]["cards"].remove(card)
    card["modified"] = now_iso()
    board["columns"][dest].setdefault("cards", []).append(card)
    kanban_save(path, board)


def cmd_move(args):
    board_flag = flagval(args, "--board")
    pos = [a for a in args if not a.startswith("-")]
    if len(pos) != 2:
        die("usage: tess kanban move <card> <col> [--board b]", 2)
    path, board, cid, card = resolve_card(pos[0], board_flag)
    dest = find_col(board, pos[1])
    if dest is None:
        die(f"no column '{pos[1]}' in {_bname(board, path)} "
            f"(columns: {_col_names(board)})", 2)
    _move(path, board, cid, card, dest)
    print(f"moved {(card.get('id') or '')[:8]} to {dest}")


def cmd_done(args):
    board_flag = flagval(args, "--board")
    pos = [a for a in args if not a.startswith("-")]
    if len(pos) != 1:
        die("usage: tess kanban done <card> [--board b]", 2)
    path, board, cid, card = resolve_card(pos[0], board_flag)
    dest = next((c for c, col in sorted_columns(board) if _is_done(c, col)), None)
    if dest is None:
        die(f"{_bname(board, path)} has no done-ish column "
            f"(columns: {_col_names(board)} — use: tess kanban move)", 2)
    _move(path, board, cid, card, dest)
    print(f"moved {(card.get('id') or '')[:8]} to {dest}")


def cmd_rm(args):
    board_flag = flagval(args, "--board")
    pos = [a for a in args if not a.startswith("-")]
    if len(pos) != 1:
        die("usage: tess kanban rm <card> [--board b]", 2)
    path, board, cid, card = resolve_card(pos[0], board_flag)
    board["columns"][cid]["cards"].remove(card)
    kanban_save(path, board)
    print(f'removed {(card.get("id") or "")[:8]} ("{card.get("title") or ""}")')


SUBS = {"new": cmd_new, "add": cmd_add, "move": cmd_move, "done": cmd_done, "rm": cmd_rm}


def main():
    require_vault()
    args = sys.argv[1:]
    if args and args[0] in SUBS:
        SUBS[args[0]](args[1:])
    else:
        cmd_bare(args)   # bare / board name (a board literally named e.g. "rm": use --board)


if __name__ == "__main__":
    main()
