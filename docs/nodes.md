# Nodes — your other machines

A node is another computer you work on: a Mac mini under the desk, a Linux box, a cloud VM.
Add it once and its name becomes a command.

```bash
tess node add mini me@100.64.0.7     set it up end to end
tess node add                        …or answer two questions
tess node                            every node: reachable · tess version · what is running there
```

`tess node add` does the whole setup, reports each step, and is safe to re-run:

| step | what happens |
|---|---|
| ssh alias | a `Host mini` block in `~/.ssh/config` (keep-alives + one reused connection), fenced by `# >>> tess node: mini` markers |
| reach it | key-based ssh. If your key isn't there yet it asks for that machine's password **once** and installs the key (it makes a key if you have none) |
| tools | checks git · rsync · python3, installs `dtach` (brew / apt / dnf / pacman) |
| tess | clones tess there and runs its installer. If the node can't clone (private repo, no internet) your checkout is pushed to it over ssh instead |
| register | adds `mini=mini` to `TESS_PEERS` in `~/.config/tess/config` |

If the machine can't be reached, nothing is left behind. If a later step fails the node is
kept and the gap is shown — fix it and run `tess node setup mini`.

Don't know the address? Run `tess node me` **on that machine**: it prints the exact
`tess node add …` line (Tailscale and LAN addresses) and tells you if ssh is off.

Already have a `Host mini` in `~/.ssh/config`? `tess node add mini` adopts it untouched.

## Use it

```bash
tess mini                    a persistent shell there
tess mini api                another one, named "api" — use a name per tab
tess mini ls                 every shell there + what is running in it and where
tess mini kill api           end one · tess mini clean (idle ones) · tess mini killall
tess mini run pnpm test      one command, with that machine's real PATH
tess mini handoff            move this folder's live session there   (see fleet.md)
tess mini back               take it back
tess mini tunnel 3000        its localhost:3000, here
tess mini pull report.md     copy files down (a ~/… path means the node's home)
tess mini pull               sweep what the agents there generated into ~/Desktop/mini-out
tess mini new <feature>      cut a worktree there
tess mini ssh                a plain ssh, no persistence
```

The shell is held by `dtach` on the node, parented to init rather than to sshd — so closing
the laptop only drops the connection and whatever was running keeps running. `tess mini`
again reattaches. `ctrl-\` detaches on purpose; `exit` ends the shell for real. The same name
from two tabs drives the *same* shell. Nothing else sits in between: no status bar, no
scrollback interception.

`tess handoff mini`, `tess tunnel mini 3000` and `tess new --on mini` are the same commands
from the other side — use whichever you remember.

## Housekeeping

```bash
tess node setup mini         re-check / repair the far side
tess node rm mini            forget it (nothing is deleted on the machine)
tess node --json             for scripts
```

A node name can't be an existing tess command. Unattended setup: with `sshpass` installed,
`SSHPASS=… tess node add …` installs the key without a prompt. Windows nodes aren't
supported directly — point a node at a WSL or Linux sshd instead.
