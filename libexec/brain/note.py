#!/usr/bin/env python3
"""tess note — create, list, and resolve vault notes (new / ls / path / show)."""
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_vault import (VAULT, HUB, FM_RE, atomic_write, confine_folder, die,  # noqa: E402
                        find_template, inside_vault, make_frontmatter, note_title,
                        rel, render_template, require_vault, resolve_notes,
                        template_dirs, template_vars, walk)
from tess_common import C  # noqa: E402

USAGE = ("usage: tess note new <name> [--in <folder>] [--template <t>] [--tags a,b] "
         "[--desc <d>] [-- body] · ls [folder] [--limit N] [--json] · "
         "path <name> · show <name>")


def _default_dir():
    inbox = os.path.join(HUB, "Inbox")
    return inbox if os.path.isdir(inbox) else VAULT


def _flag_value(args, i):
    if i + 1 >= len(args):
        die(f"{args[i]} needs a value ({USAGE})", 2)
    return args[i + 1]


def _target_folder(folder):
    return confine_folder(folder)


# ---------------- new --------------------------------------------------------

def cmd_new(args):
    body = None
    if "--" in args:
        cut = args.index("--")
        body = " ".join(args[cut + 1:]).strip()
        args = args[:cut]
    folder = template = None
    tags, desc, pos = [], "", []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--in":
            folder = _flag_value(args, i); i += 2
        elif a == "--template":
            template = _flag_value(args, i); i += 2
        elif a == "--tags":
            tags = [t.strip() for t in _flag_value(args, i).split(",") if t.strip()]; i += 2
        elif a == "--desc":
            desc = _flag_value(args, i); i += 2
        elif a.startswith("-"):
            die(f"unknown flag '{a}' ({USAGE})", 2)
        else:
            pos.append(a); i += 1
    name = " ".join(pos).strip()
    if not name:
        die(f"note needs a name ({USAGE})", 2)
    if "/" in name or os.sep in name:
        die("note names can't contain path separators (pick a folder with --in)", 2)
    if name.startswith("."):
        die("note names can't start with '.' — hidden files are invisible to tess", 2)

    tdir = _target_folder(folder) if folder else _default_dir()
    path = inside_vault(os.path.join(rel(tdir), name + ".md"))
    if os.path.exists(path):
        die(f"'{rel(path)}' already exists (append instead: tess add {name} -- <text>)", 2)

    if template:
        hits = find_template(template)
        if not hits:
            names = sorted({note_title(p) for d in template_dirs() for p in walk(d)})
            extra = f"available: {', '.join(names)}" if names else \
                "no template folders in the vault — make one, e.g. Templates/"
            die(f"no template matching '{template}' ({extra})", 2)
        if len(hits) > 1:
            for p in hits:
                print(p)
            sys.exit(3)
        try:
            raw = open(hits[0], errors="ignore").read()
        except OSError as e:
            die(f"can't read template {rel(hits[0])}: {e}", 1)
        text = render_template(raw, template_vars(title=name, filename=name + ".md"))
        m = FM_RE.match(text)
        if m:  # template keeps its own frontmatter; retitle it to the new note
            fm, n = re.subn(r"(?m)^title:.*$", lambda _: f"title: {name}",
                            m.group(0), count=1)
            if n:
                text = fm + text[m.end():]
        if body:
            text = text.rstrip("\n") + "\n\n" + body + "\n"
    else:
        text = make_frontmatter(name, tags, desc) + f"# {name}\n"
        if body:
            text += body + "\n"

    atomic_write(path, text)
    print(f"created {rel(path)}")


# ---------------- ls ---------------------------------------------------------

def cmd_ls(args):
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    limit = 50
    if "--limit" in args:
        i = args.index("--limit")
        try:
            limit = int(args[i + 1])
        except (IndexError, ValueError):
            die(f"--limit needs a number ({USAGE})", 2)
        del args[i:i + 2]
    extra = [a for a in args if a.startswith("-")]
    if extra:
        die(f"unknown flag '{extra[0]}' ({USAGE})", 2)
    folder = args[0] if args else None
    root, label = VAULT, "notes"
    if folder:
        root = _target_folder(folder)
        label = f"notes in {rel(root)}"

    notes = []
    for p in walk(root):
        try:
            notes.append((os.stat(p).st_mtime, p))
        except OSError:
            pass
    notes.sort(key=lambda t: (-t[0], t[1]))
    total = len(notes)
    rows = [{"path": rel(p), "title": note_title(p),
             "modified": datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M")}
            for mt, p in notes[:limit]]

    if as_json:
        print(json.dumps(rows, indent=2))
        return
    shown = f"{len(rows)} of {total}" if total > len(rows) else str(total)
    print(f"\n  {C.bold}{C.mag}{label}{C.r}  {C.grey}({shown}) — read one: tess note show <name>{C.r}\n")
    if not rows:
        print(f"  {C.grey}no notes here yet — create one: tess note new <name>{C.r}\n")
        return
    for r in rows:
        print(f"  {r['path']:<56} {C.grey}{r['modified'][:10]}{C.r}")
    print()


# ---------------- path / show ------------------------------------------------

def _resolve_one(query, as_json):
    hits = resolve_notes(query)
    if not hits:
        die(f"no note matching '{query}' (create it: tess note new {query})", 2)
    if len(hits) > 1:
        if as_json:
            print(json.dumps([{"path": p} for p in hits], indent=2))
        else:
            for p in hits:
                print(p)
        sys.exit(3)
    return hits[0]


def cmd_path(args):
    as_json = "--json" in args
    query = " ".join(a for a in args if a != "--json").strip()
    if not query:
        die(f"which note? ({USAGE})", 2)
    p = _resolve_one(query, as_json)
    if as_json:
        print(json.dumps({"path": p}, indent=2))
    else:
        print(p)


def cmd_show(args):
    as_json = "--json" in args
    query = " ".join(a for a in args if a != "--json").strip()
    if not query:
        die(f"which note? ({USAGE})", 2)
    p = _resolve_one(query, as_json)
    try:
        sys.stdout.write(open(p, errors="ignore").read())
    except OSError as e:
        die(f"can't read {rel(p)}: {e}", 1)


def main():
    argv = sys.argv[1:]
    sub = argv[0] if argv else ""
    if sub in ("", "-h", "--help", "help"):
        die(USAGE, 2)
    require_vault()
    rest = argv[1:]
    if sub == "new":
        cmd_new(rest)
    elif sub == "ls":
        cmd_ls(rest)
    elif sub == "path":
        cmd_path(rest)
    elif sub == "show":
        cmd_show(rest)
    else:
        die(f"unknown subcommand '{sub}' ({USAGE})", 2)


if __name__ == "__main__":
    main()
