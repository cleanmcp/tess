#!/usr/bin/env python3
"""tess vault … / tess canvas … — orientation + structure for the notes vault.

Subcommands (argv[1], default "map"):
  map [--json]                vault orientation: folders, boards, bases, templates, canvases
  folders [--json]            flat folder list with per-folder recursive note counts
  mkdir <rel/path>            create a folder inside the vault
  init <path>                 scaffold a NEW Lokus-compatible workspace (no vault needed)
  canvas [ls|new] …           list canvases / create an empty .excalidraw
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_common import C, short                                  # noqa: E402
from tess_vault import (VAULT, HUB, atomic_write, die, folders,   # noqa: E402
                        inside_vault, kanban_files, kanban_save, new_board,
                        read_note, rel, require_vault, template_dirs, walk)

CANVAS_EXTS = (".excalidraw", ".canvas")

# Exact empty-document shape Lokus writes (createEmptyExcalidrawData in
# src/core/canvas/manager.js) — plain Excalidraw JSON, field-for-field.
EMPTY_CANVAS = {"type": "excalidraw", "version": 2, "source": "lokus",
                "elements": [], "appState": {"viewBackgroundColor": "transparent"},
                "files": {}}

HOME = os.path.expanduser("~")


def tilde(p):
    return p.replace(HOME, "~", 1) if p.startswith(HOME) else p


def rel_disp(p):
    """Vault-relative display path; the vault root itself shows as '.'."""
    return "." if os.path.abspath(p) == os.path.abspath(VAULT) else rel(p)


def default_new_note_dir():
    inbox = os.path.join(HUB, "Inbox")
    return inbox if os.path.isdir(inbox) else VAULT


def note_counts(all_md):
    """({rel folder -> recursive .md count}, count of root-direct .md files)."""
    counts, root_direct = {}, 0
    for p in all_md:
        parts = rel(p).split(os.sep)[:-1]
        if not parts:
            root_direct += 1
        for i in range(1, len(parts) + 1):
            key = os.sep.join(parts[:i])
            counts[key] = counts.get(key, 0) + 1
    return counts, root_direct


def base_names():
    d = os.path.join(VAULT, ".lokus", "bases")
    try:
        return sorted(f[:-len(".base")] for f in os.listdir(d) if f.endswith(".base"))
    except OSError:
        return []


def start_here_lines():
    path = os.path.join(VAULT, "START-HERE.md")
    if not os.path.isfile(path):
        return []
    _, body, _ = read_note(path)
    out = []
    for line in body.splitlines():
        if line.strip():
            out.append(line.strip())
        if len(out) >= 5:
            break
    return out


# ---------------- map -------------------------------------------------------

def cmd_map(args):
    require_vault()
    as_json = "--json" in args
    all_md = list(walk())
    all_dirs = folders()
    counts, root_direct = note_counts(all_md)
    boards = [rel(p) for p in kanban_files()]
    canvases = [rel(p) for p in walk(exts=CANVAS_EXTS)]
    base_files = [rel(p) for p in walk(exts=(".base",))]   # stray .base outside .lokus
    tdirs = [rel(d) for d in template_dirs()]
    bases = base_names()
    start = start_here_lines()
    new_dir = rel_disp(default_new_note_dir())

    if as_json:
        print(json.dumps({
            "vault": VAULT, "hub": HUB, "default_new_note_dir": new_dir,
            "folders": [{"path": d, "notes": counts.get(d, 0)} for d in all_dirs],
            "boards": boards, "bases": bases, "templates": tdirs,
            "canvases": canvases, "start_here": "\n".join(start) or None,
        }, indent=2))
        return

    print(f"\n  {C.bold}{C.mag}vault map{C.r}  {C.grey}({tilde(VAULT)} · "
          f"{len(all_md)} notes · {len(all_dirs)} folders){C.r}\n")
    print(f"  write here when unsure: {C.cyan}{new_dir}{C.r}\n")

    top = [d for d in all_dirs if os.sep not in d]
    if not top and not all_md:
        print(f"  {C.grey}empty vault — create a note: tess add <name> -- <text>{C.r}")
    for d in top:
        flags = [f"board:{os.path.basename(b)[:-len('.kanban')]}"
                 for b in boards if b.startswith(d + os.sep)]
        n_bases = sum(1 for b in base_files if b.startswith(d + os.sep))
        if n_bases:
            flags.append(f"{n_bases} bases")
        if d in tdirs:
            flags.append("templates")
        n_canvas = sum(1 for c in canvases if c.startswith(d + os.sep))
        if n_canvas:
            flags.append(f"canvas:{n_canvas}")
        tail = f"  {C.grey}· " + " · ".join(flags) + f"{C.r}" if flags else ""
        print(f"  {C.cyan}{d + '/':<26}{C.r}{counts.get(d, 0):>4} notes{tail}")
        subs = [s for s in all_dirs
                if s.startswith(d + os.sep) and s.count(os.sep) == d.count(os.sep) + 1
                and counts.get(s, 0) >= 3]
        for s in subs:
            print(f"    {os.path.basename(s) + '/':<24}{counts.get(s, 0):>4} notes")
    if root_direct:
        print(f"  {'./':<26}{root_direct:>4} notes")

    print(f"\n  {C.bold}boards{C.r}")
    if boards:
        for b in boards:
            print(f"    {b}")
    else:
        print(f"    {C.grey}none yet — tess kanban new <name>{C.r}")

    print(f"  {C.bold}bases{C.r}")
    if bases:
        for b in bases:
            print(f"    {b}")
    else:
        print(f"    {C.grey}none yet — Lokus creates them in .lokus/bases "
              f"(ad-hoc: tess base query){C.r}")

    print(f"  {C.bold}templates{C.r}")
    if tdirs:
        for t in tdirs:
            print(f"    {t}")
    else:
        print(f"    {C.grey}none — a vault-root folder named Templates/ becomes one{C.r}")

    print(f"  {C.bold}canvases{C.r}  {len(canvases)}"
          + (f"  {C.grey}(new: tess canvas new <name>){C.r}" if not canvases else ""))

    if start:
        print(f"\n  conventions (START-HERE.md):")
        for line in start:
            print(f"    {C.grey}{short(line, 76)}{C.r}")
    print()


# ---------------- folders ---------------------------------------------------

def cmd_folders(args):
    require_vault()
    as_json = "--json" in args
    counts, _ = note_counts(list(walk()))
    rows = [{"path": d, "notes": counts.get(d, 0)} for d in folders()]
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    print(f"\n  {C.bold}{C.mag}vault folders{C.r}  {C.grey}({len(rows)}){C.r}\n")
    if not rows:
        print(f"  {C.grey}no folders yet — tess vault mkdir <name>{C.r}\n")
        return
    for r in rows:
        print(f"  {C.cyan}{r['path'] + '/':<40}{C.r} {C.grey}{r['notes']} notes{C.r}")
    print()


# ---------------- mkdir -----------------------------------------------------

def cmd_mkdir(args):
    require_vault()
    pos = [a for a in args if not a.startswith("-")]
    if len(pos) != 1:
        die("usage: tess vault mkdir <rel/path>", 2)
    full = inside_vault(pos[0])
    if os.path.exists(full):
        die(f"'{rel(full)}' already exists (see: tess vault folders)", 2)
    os.makedirs(full, exist_ok=False)
    print(f"created {rel(full)}/")


# ---------------- init (does NOT require the vault — bootstraps one) --------

def cmd_init(args):
    pos = [a for a in args if not a.startswith("-")]
    if len(pos) != 1:
        die("usage: tess vault init <path>", 2)
    p = os.path.abspath(os.path.expanduser(pos[0]))
    lokus = os.path.join(p, ".lokus")
    if os.path.isdir(lokus):
        print(f"already a workspace: {tilde(p)}")
        return
    if os.path.exists(p) and not os.path.isdir(p):
        die(f"'{tilde(p)}' exists and is not a directory (pick a new path)", 2)
    if os.path.isdir(p) and os.listdir(p):
        die(f"'{tilde(p)}' exists and is not empty — refusing to adopt "
            f"(pick a new path, or add .lokus/ yourself)", 2)
    notes = os.path.join(p, "notes")
    board = os.path.join(p, "Tasks.kanban")
    os.makedirs(lokus, exist_ok=True)
    os.makedirs(notes, exist_ok=True)
    kanban_save(board, new_board("Tasks"))
    for created in (lokus + os.sep, notes + os.sep, board):
        print(f"created {tilde(created)}")


# ---------------- canvas ----------------------------------------------------

def canvas_ls(args):
    require_vault()
    as_json = "--json" in args
    rows = []
    for p in walk(exts=CANVAS_EXTS):
        try:
            mtime = os.stat(p).st_mtime
        except OSError:
            mtime = 0
        rows.append({"path": rel(p), "modified": mtime,
                     "legacy": p.endswith(".canvas")})
    rows.sort(key=lambda r: r["modified"], reverse=True)
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    print(f"\n  {C.bold}{C.mag}canvases{C.r}  {C.grey}({len(rows)}){C.r}\n")
    if not rows:
        print(f"  {C.grey}no canvases yet — tess canvas new <name>{C.r}\n")
        return
    from datetime import datetime
    for r in rows:
        day = datetime.fromtimestamp(r["modified"]).strftime("%Y-%m-%d") if r["modified"] else "?"
        mark = f"  {C.yellow}legacy{C.r}" if r["legacy"] else ""
        print(f"  {C.cyan}{r['path']:<44}{C.r} {C.grey}{day}{C.r}{mark}")
    print()


def canvas_new(args):
    require_vault()
    folder = None
    if "--in" in args:
        i = args.index("--in")
        if i + 1 >= len(args):
            die("--in needs a folder", 2)
        folder = args[i + 1]
        del args[i:i + 2]
    pos = [a for a in args if not a.startswith("-")]
    if not pos:
        die("usage: tess canvas new <name> [--in <folder>]", 2)
    name = " ".join(pos).removesuffix(".excalidraw").strip()
    if not name or "/" in name or os.sep in name:
        die("canvas name can't contain path separators (use --in <folder>)", 2)
    dest = inside_vault(folder) if folder else VAULT
    if not os.path.isdir(dest):
        die(f"no folder '{folder}' (see: tess vault folders)", 2)
    path = os.path.join(dest, name + ".excalidraw")
    if os.path.exists(path):
        die(f"'{rel(path)}' already exists", 2)
    atomic_write(path, json.dumps(EMPTY_CANVAS, indent=2) + "\n")
    print(f"created {rel(path)}")
    print(f"  {C.grey}agents: this is plain Excalidraw JSON — "
          f"write elements directly to draw{C.r}")


def cmd_canvas(args):
    sub = args[0] if args and not args[0].startswith("-") else "ls"
    rest = args[1:] if args and not args[0].startswith("-") else args
    if sub in ("ls", "list"):
        canvas_ls(rest)
    elif sub == "new":
        canvas_new(rest)
    else:
        die(f"unknown canvas command '{sub}' (usage: tess canvas [ls | new <name> [--in <folder>]])", 2)


# ---------------- dispatch --------------------------------------------------

def main():
    args = sys.argv[1:]
    cmd = args[0] if args and not args[0].startswith("-") else "map"
    rest = args[1:] if args and not args[0].startswith("-") else args
    if cmd == "map":
        cmd_map(rest)
    elif cmd == "folders":
        cmd_folders(rest)
    elif cmd == "mkdir":
        cmd_mkdir(rest)
    elif cmd == "init":
        cmd_init(rest)
    elif cmd == "canvas":
        cmd_canvas(rest)
    else:
        die(f"unknown vault command '{cmd}' "
            f"(usage: tess vault [map|folders|mkdir|init] · tess canvas)", 2)


if __name__ == "__main__":
    main()
