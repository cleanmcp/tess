#!/usr/bin/env python3
"""tess <node> pull — copy files from a node down to this machine.

    tess mini pull <path>…        those remote files or dirs, into the current folder
    tess mini pull <path> --into <dir>
    tess mini pull                sweep what the agents there generated
    tess mini pull --all          …including json/log/txt/sql, not just reports and images
    tess mini pull --days N       look back N days (default 7)
    tess mini pull --dry-run      list what would come over

Agents on a node write reports and screenshots into their session scratchpads
and job dirs, which never leave that machine. The sweep copies the
deliverable-shaped ones into ~/Desktop/<node>-out/<project>/, skipping anything
already here with the same mtime. Source files are left alone.

A pasted "~/…" means the NODE's home. The first argument is the ssh target,
passed by `tess <node> pull`; TESS_NODE_LABEL names it in messages.
"""
import argparse, io, json, os, pathlib, shlex, subprocess, sys, tarfile

HOST = ""                      # ssh target — set in main()
LABEL = "node"
DEST = pathlib.Path.home() / "Desktop" / "node-out"
DELIVERABLE = {"md", "png", "jpg", "jpeg", "gif", "webp", "pdf", "csv", "tsv",
               "xlsx", "xls", "xlsm", "ods", "numbers", "docx", "pptx", "html", "svg"}
ALSO = {"json", "log", "txt", "sql", "jsonl", "yaml", "yml"}
MAX_BYTES = 25 * 1024 * 1024

# Runs on the node. Walks the roots and reports candidates as JSON.
REMOTE = r'''
import json, os, sys, time
exts, days, maxb = set(json.loads(sys.argv[1])), float(sys.argv[2]), int(sys.argv[3])
cut = time.time() - days * 86400
home = os.path.expanduser("~")
roots = ["/private/tmp/claude-%d" % os.getuid(), "/tmp/claude-%d" % os.getuid(), os.path.join(home, ".claude", "jobs"),
         os.path.join(home, "out")]
skip = {"node_modules", ".git", "__pycache__", ".venv", "dist", "build"}
out = []
for root in roots:
    if not os.path.isdir(root):
        continue
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
            if ext not in exts:
                continue
            p = os.path.join(dirpath, fn)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if st.st_mtime < cut or st.st_size > maxb or st.st_size == 0:
                continue
            out.append({"path": p, "mtime": int(st.st_mtime), "size": st.st_size})
print(json.dumps(out))
'''


def session_of(path):
    """The 8-char session id in a scratchpad path, for disambiguating names."""
    for part in path.split("/"):
        if len(part) == 36 and part.count("-") == 4:
            return part[:8]
    return "x"


def project_of(path):
    """A short folder name for where this came from, for a tidy destination."""
    parts = path.split("/")
    for i, part in enumerate(parts):
        if part.startswith("-Users-"):
            slug = part.split("-worktrees-", 1)[-1] if "-worktrees-" in part else "home"
            return slug.strip("-") or "home"
        if part == "jobs" and i + 1 < len(parts):
            return "jobs-" + parts[i + 1]
    return "misc"


def fetch(paths, into, dry_run):
    """Copy named remote paths (files or dirs) straight down, keeping only the
    last component, so a pasted scratchpad path lands as a plain filename."""
    # Expand a pasted "~/..." against the NODE's home, not this laptop's, and
    # do it here rather than in the remote shell: zsh applies the :A modifier
    # before tilde expansion, which yields /Users/<them>/~/...
    home = subprocess.run(["ssh", HOST, "printf %s \"$HOME\""],
                          capture_output=True, text=True)
    if home.returncode != 0:
        print(f"{LABEL} unreachable: {home.stderr.strip()[:200]}", file=sys.stderr)
        return 1
    remote_home = home.stdout.strip()

    # zsh expands a bare ~/... against THIS laptop's home before the function
    # ever runs, so "~/Downloads/x" arrives as "/Users/<me>/Downloads/x". Try
    # the path as given and, failing that, the same path under the node's home,
    # and keep whichever actually exists over there.
    local_home = str(pathlib.Path.home())
    candidates = []
    for raw in paths:
        q = raw.strip().rstrip("/") or "/"
        tries = [remote_home + q[1:]] if (q == "~" or q.startswith("~/")) else [q]
        if q.startswith(local_home + "/"):
            tries.append(remote_home + q[len(local_home):])
        candidates.append((raw, tries))

    # One remote python call: for each path, report the first candidate that
    # exists, or a blank line if none do.
    pick = ("import json,os,sys\n"
            "for group in json.loads(sys.argv[1]):\n"
            "    print(next((t for t in group if os.path.exists(t)), ''))\n")
    probe = subprocess.run(
        ["ssh", HOST, "python3 - " + shlex.quote(
            json.dumps([tries for _, tries in candidates]))],
        input=pick, capture_output=True, text=True)
    if probe.returncode != 0:
        print(f"{LABEL} unreachable: {probe.stderr.strip()[:200]}", file=sys.stderr)
        return 1

    lines = probe.stdout.split("\n")
    resolved, missing = [], []
    for i, (raw, tries) in enumerate(candidates):
        hit = lines[i].strip() if i < len(lines) else ""
        (resolved.append(hit) if hit else missing.append((raw, tries)))

    for raw, tries in missing:
        where = " or ".join(tries)
        print(f"not on {LABEL}: {where}", file=sys.stderr)
    if not resolved:
        return 1

    if dry_run:
        for r in resolved:
            print(f"{r}  ->  {into / os.path.basename(r.rstrip('/'))}")
        return 0

    into.mkdir(parents=True, exist_ok=True)
    rc = 0
    for r in resolved:
        parent, name = os.path.dirname(r), os.path.basename(r.rstrip("/"))
        tar = subprocess.run(
            ["ssh", HOST, "COPYFILE_DISABLE=1 tar -cf - -C "
             f"{shlex.quote(parent)} {shlex.quote(name)}"],
            capture_output=True)
        if tar.returncode != 0:
            print(f"{r}: {tar.stderr.decode().strip()[:160]}", file=sys.stderr)
            rc = 1
            continue
        with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as tf:
            safe = [m for m in tf.getmembers()
                    if not os.path.basename(m.name).startswith("._")
                    and not os.path.isabs(m.name)
                    and ".." not in pathlib.PurePath(m.name).parts
                    and (m.isfile() or m.isdir())]
            tf.extractall(into, members=safe)
        print(into / name)
    return rc


def main():
    global HOST, LABEL, DEST
    ap = argparse.ArgumentParser(prog="tess <node> pull")
    ap.add_argument("host", help=argparse.SUPPRESS)
    ap.add_argument("paths", nargs="*", help="remote path(s) to fetch; "
                    "with none, sweep the agents' output dirs")
    ap.add_argument("-d", "--into", default=".", help="where named paths land "
                    "(default: here)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    HOST = args.host
    LABEL = os.environ.get("TESS_NODE_LABEL") or HOST
    DEST = pathlib.Path.home() / "Desktop" / f"{LABEL}-out"

    if args.paths:
        return fetch(args.paths, pathlib.Path(args.into).expanduser(), args.dry_run)

    exts = sorted(DELIVERABLE | ALSO) if args.all else sorted(DELIVERABLE)
    # ssh hands the argv to a remote shell, so quote it rather than letting
    # the JSON brackets be read as a glob.
    remote_cmd = " ".join(shlex.quote(a) for a in
                          ["python3", "-", json.dumps(exts), str(args.days), str(MAX_BYTES)])
    probe = subprocess.run(["ssh", HOST, remote_cmd],
                           input=REMOTE, capture_output=True, text=True)
    if probe.returncode != 0:
        print(f"{LABEL} unreachable: {probe.stderr.strip()[:200]}", file=sys.stderr)
        return 1
    try:
        found = json.loads(probe.stdout)
    except json.JSONDecodeError:
        print(f"unexpected reply: {probe.stdout[:200]}", file=sys.stderr)
        return 1

    # Two sessions in one project can both write "report.md"; keep both by
    # prefixing the loser with its session id instead of overwriting.
    claimed = {}
    wanted = []
    for f in sorted(found, key=lambda x: x["path"]):
        local = DEST / project_of(f["path"]) / os.path.basename(f["path"])
        if claimed.get(local, f["path"]) != f["path"]:
            stem, n = f"{session_of(f['path'])}-{local.name}", 2
            local = local.with_name(stem)
            while claimed.get(local, f["path"]) != f["path"]:
                local = local.with_name(f"{n}-{stem}")
                n += 1
        claimed[local] = f["path"]
        if local.exists() and int(local.stat().st_mtime) >= f["mtime"]:
            continue
        wanted.append((f, local))

    if not wanted:
        print(f"nothing new ({len(found)} files checked)")
        return 0

    if args.dry_run:
        for f, local in wanted:
            print(f"{f['size']:>9}  {f['path']}  ->  {local}")
        print(f"\n{len(wanted)} file(s) would be pulled")
        return 0

    # One tar stream rather than one ssh per file.
    names = "\0".join(f["path"] for f, _ in wanted)
    tar = subprocess.run(
        ["ssh", HOST, "COPYFILE_DISABLE=1 tar -cf - --null -T -"],
        input=names.encode(), capture_output=True)
    if tar.returncode != 0:
        print(f"copy failed: {tar.stderr.decode()[:200]}", file=sys.stderr)
        return 1

    by_src = {f["path"].lstrip("/"): (f, local) for f, local in wanted}
    pulled = 0
    with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as tf:
        for member in tf:
            entry = by_src.get(member.name.lstrip("./").lstrip("/"))
            if not entry or not member.isfile():
                continue
            f, local = entry
            local.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            local.write_bytes(src.read())
            os.utime(local, (f["mtime"], f["mtime"]))
            pulled += 1
            print(f"{local.relative_to(DEST)}")
    print(f"\npulled {pulled} file(s) into {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
