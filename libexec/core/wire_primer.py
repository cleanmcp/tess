#!/usr/bin/env python3
"""Inject / refresh / remove the tess primer block in an agent instructions file.

usage: wire_primer.py <instructions-file> <agent-primer.md> [--undo]

The block is fenced by HTML comments, so the rest of the file (the user's own instructions)
is never touched, and a re-run replaces the block in place rather than appending a second copy.
"""
import os
import re
import sys

PAT = re.compile(r"<!-- tess-agent-primer.*?<!-- /tess-agent-primer -->\n?", re.S)


def main():
    args = [a for a in sys.argv[1:] if a and a != "--undo"]
    undo = "--undo" in sys.argv[1:]
    if len(args) < 2:
        print("usage: wire_primer.py <file> <primer.md> [--undo]", file=sys.stderr)
        return 2
    f, src = args[0], args[1]
    short = f.replace(os.path.expanduser("~"), "~")

    txt = open(f).read() if os.path.exists(f) else ""

    if undo:
        if not PAT.search(txt):
            print("  · %s (no primer to remove)" % short)
            return 0
        open(f, "w").write(PAT.sub("", txt).rstrip() + "\n")
        print("  ✓ removed the tess primer from %s" % short)
        return 0

    body = open(src).read().rstrip() + "\n"
    os.makedirs(os.path.dirname(f) or ".", exist_ok=True)
    if PAT.search(txt):
        if PAT.search(txt).group(0).rstrip() == body.rstrip():
            print("  · %s (already current)" % short)
            return 0
        open(f, "w").write(PAT.sub(lambda _: body, txt))
        print("  ✓ refreshed the tess primer in %s" % short)
    else:
        open(f, "w").write(txt.rstrip() + ("\n\n" if txt.strip() else "") + body)
        print("  ✓ wired tess into %s" % short)
    return 0


if __name__ == "__main__":
    sys.exit(main())
