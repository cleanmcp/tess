#!/usr/bin/env python3
# _tess-comms.py — the lead's voice + mailbox. The user IS @bigboss.
#   tell <agent|feature|all> [--intent I] [--raw] -- <msg>   (or stdin)
#       send a message as bigboss. Any @word in the BODY that names a live
#       agent gets a zero-width space injected (invisible) so hcom never
#       misparses report content — emails/handles arrive intact and nobody
#       gets accidentally DM'd. --raw skips that escaping.
#   inbox [--all] [--peek] [--json]
#       unread messages for the lead: @bigboss mentions + agent broadcasts,
#       tracked by a cursor in ~/.config/tess/state. --peek doesn't mark read.
import base64
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _tess_agents import agents_under, hcom, list_agents, scrub

WORKTREE_ROOT = (os.environ.get("TESS_WORKTREE_ROOT") or os.path.expanduser("~/worktrees")).rstrip("/")
STATE_DIR = os.path.expanduser("~/.config/tess/state")
CURSOR = os.path.join(STATE_DIR, "inbox.cursor")
LEAD_FILE = os.path.join(STATE_DIR, "lead")
ZWSP = "\u200b"


def die(msg, code=1):
    print(f"tess: {msg}", file=sys.stderr)
    sys.exit(code)


def lead_name():
    try:
        return open(LEAD_FILE).read().strip() or "bigboss"
    except OSError:
        return "bigboss"


def escape_mentions(text, keep=()):
    """Neutralize @words that hcom would deliver as mentions: live agent names,
    tag fan-outs (@tag-), and the lead. Content stays visually identical."""
    names = {a["name"] for a in list_agents()} | {a.get("base_name") for a in list_agents()}
    names |= {lead_name(), "bigboss"}
    names.discard(None)

    def sub(m):
        word = m.group(1)
        if word in keep:
            return m.group(0)
        if word in names or word.endswith("-") or any(n.startswith(word) for n in names):
            return "@" + ZWSP + word
        return m.group(0)

    return re.sub(r"@([\w.-]+)", sub, text)


def events_query(*flags):
    r = hcom("events", "--last", "500", *flags)
    out = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def cmd_tell(args):
    text = None
    if "--" in args:
        i = args.index("--")
        text = " ".join(args[i + 1:])
        args = args[:i]
    intent, raw = "request", False
    pos = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--intent":
            if i + 1 >= len(args):
                die("--intent needs a value")
            intent = args[i + 1]
            i += 1
        elif a == "--raw":
            raw = True
        elif a.startswith("-"):
            die(f"unknown flag '{a}' (usage: tess tell <agent|feature|all> [--intent I] [--raw] -- <msg>)")
        else:
            pos.append(a)
        i += 1
    if len(pos) != 1:
        die("usage: tess tell <agent|feature|all> [--intent I] [--raw] -- <msg>")
    target = pos[0]
    if text is None:
        if sys.stdin.isatty():
            die("no message: put it after -- or pipe it on stdin")
        text = sys.stdin.read()
    if not text.strip():
        die("empty message")

    if target == "all":
        addrs = []
    elif os.path.isdir(os.path.join(WORKTREE_ROOT, target)):
        feat_agents = agents_under(os.path.join(WORKTREE_ROOT, target))
        if not feat_agents:
            die(f"no agents running in feature '{target}'")
        addrs = ["@" + a["name"] for a in feat_agents]
    else:
        addrs = ["@" + target]

    if not raw:
        text = escape_mentions(text)
    b64 = base64.b64encode(text.encode()).decode()
    r = hcom("send", *addrs, "--from", lead_name(), "--intent", intent, "--base64", b64)
    if r.returncode != 0:
        die(f"send failed: {(r.stderr or r.stdout).strip()[:300]}", 2)
    print(f"→ {' '.join(addrs) or 'everyone'} (as {lead_name()}, {intent}): "
          f"{' '.join(text.split())[:80]}")


def read_cursor():
    try:
        return int(open(CURSOR).read().strip())
    except (OSError, ValueError):
        return 0


def cmd_inbox(args):
    show_all = "--all" in args
    peek = "--peek" in args
    as_json = "--json" in args
    lead = lead_name()
    cur = 0 if show_all else read_cursor()

    seen, msgs = set(), []
    for ev in (events_query("--type", "message", "--mention", lead)
               + events_query("--type", "message", "--mention", "bigboss")
               + events_query("--sql", "msg_scope='broadcast'")):
        eid = ev.get("id")
        d = ev.get("data", {})
        if eid in seen or eid is None or eid <= cur:
            continue
        seen.add(eid)
        frm = d.get("from", "?")
        if (ev.get("instance") or "").startswith("sys_") or frm in (lead, "bigboss"):
            continue
        msgs.append({"id": eid, "ts": ev.get("ts", ""), "from": frm,
                     "intent": d.get("intent"), "text": scrub(d.get("text", ""))})
    msgs.sort(key=lambda m: m["id"])

    if as_json:
        print(json.dumps(msgs, indent=2))
    elif not msgs:
        print("inbox zero — no " + ("messages at all" if show_all else "unread agent reports") + ".")
    else:
        for m in msgs:
            head = f"[#{m['id']}] {m['ts'][11:16]} {m['from']}"
            if m["intent"]:
                head += f" ({m['intent']})"
            print(head)
            print("  " + m["text"].replace("\n", "\n  "))
            print()
        print(f"{len(msgs)} message(s). reply: tess tell <agent> -- <msg>")
    if msgs and not peek and not show_all:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(CURSOR, "w") as f:
            f.write(str(max(m["id"] for m in msgs)))


def main():
    args = sys.argv[1:]
    if not args:
        die("usage: _tess-comms.py tell|inbox …")
    sub = args.pop(0)
    if sub == "tell":
        cmd_tell(args)
    elif sub == "inbox":
        cmd_inbox(args)
    else:
        die(f"unknown subcommand '{sub}'")


if __name__ == "__main__":
    main()
