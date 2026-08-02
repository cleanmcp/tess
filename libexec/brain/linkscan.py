#!/usr/bin/env python3
"""tess links — wiki-link graph over the vault.

  tess links <note…> [--json]     outlinks + backlinks for one note
  tess links --broken [--json]    every [[target]] that resolves to nothing

Exit codes: 0 ok · 1 unconfigured vault · 2 usage/not-found · 3 ambiguous
(candidates one per line on stdout; with --json a JSON array).
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from tess_vault import (die, extract_links, link_targets_index, rel,  # noqa: E402
                        require_vault, resolve_link, resolve_notes, walk)
from tess_common import C, short  # noqa: E402


def scan_all_links():
    """{abs note path: [(target, alias, embed), …]} for every note, one pass."""
    out = {}
    for p in walk():
        try:
            text = open(p, errors="ignore").read()
        except OSError:
            continue
        out[p] = extract_links(text)
    return out


def cmd_note(query, as_json):
    hits = resolve_notes(query)
    if not hits:
        die(f"no note matching '{query}' (see: tess note ls)", 2)
    if len(hits) > 1:
        if as_json:
            print(json.dumps([{"path": p} for p in hits], indent=2))
        else:
            for p in hits:
                print(p)
        sys.exit(3)
    note = hits[0]
    idx = link_targets_index()
    all_links = scan_all_links()

    outlinks = []
    for target, _alias, embed in all_links.get(note, []):
        resolved = resolve_link(target, idx)
        outlinks.append({"target": target,
                         "resolved": rel(resolved[0]) if resolved else None,
                         "embed": embed})

    backlinks = []
    for src, links in all_links.items():
        if src == note:
            continue
        count = embeds = 0
        for target, _alias, embed in links:
            if note in resolve_link(target, idx):
                count += 1
                embeds += 1 if embed else 0
        if count:
            backlinks.append({"note": rel(src), "count": count, "_embeds": embeds})
    backlinks.sort(key=lambda b: (-b["count"], b["note"]))

    if as_json:
        print(json.dumps({"note": rel(note), "outlinks": outlinks,
                          "backlinks": [{"note": b["note"], "count": b["count"]}
                                        for b in backlinks]}, indent=2))
        return

    print(f"\n  {C.bold}{C.mag}links: {rel(note)}{C.r}  "
          f"{C.grey}({len(outlinks)} out · {len(backlinks)} in){C.r}\n")
    print(f"  {C.bold}outlinks{C.r} {C.grey}({len(outlinks)}){C.r}")
    if not outlinks:
        print(f"    {C.grey}none — link notes with [[name]] in the body{C.r}")
    for o in outlinks:
        label = ("!" if o["embed"] else " ") + short(o["target"], 39)
        if o["resolved"]:
            print(f"    {C.cyan}{label:<40}{C.r} {C.grey}→{C.r} {o['resolved']}")
        else:
            print(f"    {C.cyan}{label:<40}{C.r} {C.grey}→{C.r} {C.red}?unresolved{C.r}")
    print(f"\n  {C.bold}backlinks{C.r} {C.grey}({len(backlinks)}){C.r}")
    if not backlinks:
        print(f"    {C.grey}no other note links here yet{C.r}")
    for b in backlinks:
        times = f"  ×{b['count']}" if b["count"] > 1 else ""
        emb = f"  {C.yellow}(embedded){C.r}" if b["_embeds"] else ""
        print(f"    {b['note']}{C.grey}{times}{C.r}{emb}")
    print()


def cmd_broken(as_json):
    idx = link_targets_index()
    rows = []
    for src, links in sorted(scan_all_links().items()):
        for target, _alias, embed in links:
            if not resolve_link(target, idx):
                rows.append({"note": rel(src), "target": target, "embed": embed})
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    print(f"\n  {C.bold}{C.mag}broken links{C.r}  {C.grey}({len(rows)}){C.r}\n")
    if not rows:
        print(f"  {C.grey}none — every [[target]] resolves to a note{C.r}\n")
        return
    for r in rows:
        print(f"  {r['note']}: {C.red}[[{r['target']}]]{C.r}")
    print(f"\n  {C.grey}fix: create the note (tess note new <name>) or edit the link{C.r}\n")


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    require_vault()
    if "--broken" in args:
        cmd_broken(as_json)
        return
    query = " ".join(a for a in args if not a.startswith("-")).strip()
    if not query:
        die("usage: tess links <note> [--json] | tess links --broken [--json]", 2)
    cmd_note(query, as_json)


if __name__ == "__main__":
    main()
