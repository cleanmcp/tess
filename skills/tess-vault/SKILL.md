---
name: tess-vault
description: Use tess to read and write the user's markdown knowledge base (their vault) — notes, people/company intel, kanban boards, tasks and follow-ups inside notes, database-style queries, wiki links/backlinks, canvases. Trigger when the user mentions their notes, vault, knowledge base, second brain, Lokus, Obsidian, wiki links, backlinks, kanban board, "remember this", "write that down", "add to my notes", "which folder should this go in", "track this follow-up in my notes", or asks about a person/company/topic they keep notes on. Also trigger before creating or editing any .md/.kanban/.base/.excalidraw file inside the user's vault — tess writes app-valid files; hand-rolled ones can break the vault app.
---

# The vault, via tess

The user's knowledge base is a folder of markdown (`TESS_VAULT`) — possibly a Lokus/Obsidian
vault. tess is the interface: it knows the folder conventions, writes app-valid files, and
never needs the app running.

**Check it exists first.** `command -v tess`. Then `tess vault` — if it says no vault is
configured, tell the user (point them at `TESS_VAULT` in `~/.config/tess/config`); don't
improvise a notes folder somewhere else.

## Three task systems — don't mix them up

| Command | What it is | Lives in |
|---|---|---|
| `tess todo` | the CODING checklist shared across agent sessions (see the tess-worktrees skill) | `~/.config/tess/state` — not the vault |
| `tess tasks` | checkboxes inside the user's NOTES — follow-ups, reminders, reading lists | vault `.md` files |
| `tess kanban` | project boards (`.kanban` files) the vault app renders as kanban | vault board files |

"Add a todo" while coding → `tess todo add`. "Track this follow-up with Sam" → it belongs in
notes (`tess tasks` / `tess add`). "Put it on the board" → `tess kanban add`.

## Orient first

```bash
tess vault            # the map: folders + note counts, boards, bases, templates,
                      # conventions — and "write here when unsure: <dir>"
tess brief            # the user's NOW note — what's currently going on
```

`tess vault --json` gives `default_new_note_dir` — that is the answer to "which folder"
when nothing better fits. Run `tess vault folders` to pick a better-fitting one.

## Where to write — the routing table

- A person → `tess person <name> -- <desc>` · a company → `tess company <name> -- <desc>`
- Append a fact/update to an existing note → `tess add <name> -- <text>` (creates it if new)
- Quick timestamped capture → `tess log -- <text>`
- A real new document → `tess note new <name> [--in <folder>] [--template <t>] [--tags a,b]`
  — pick the folder from `tess vault folders`; when unsure, omit `--in` (lands in the
  default). Notes get proper frontmatter automatically — never write it by hand.

## Reading and finding notes

```bash
tess <name>              # read a note by name (person, company, topic)
tess note show <name>    # same, but works when the name collides with a tess command
tess note path <name>    # resolve to a file path (for editing with your own tools)
tess note ls [folder]    # newest notes
tess links <note>        # backlinks + outlinks · tess links --broken = dead links
```

Reading the file directly after `tess note path` is fine — that's what it's for.

## Boards, tasks, queries, canvases

```bash
tess kanban                          # render the board (or list them)
tess kanban add "title" --col "In Progress" --due 2026-08-15
tess kanban move <card> <col> · done <card> · rm <card> · new <name>

tess tasks [folder|note]             # every open checkbox in notes ([ ] [/] [!] [?] [>])
tess tasks done "<match>"            # check one off in its source file

tess base query --where "tags=person" --sort modified:desc --cols title,path
tess bases · tess base <name>        # saved Lokus base views, executed

tess canvas · tess canvas new <name> # Excalidraw canvases — plain Excalidraw JSON,
                                     # so you may write elements directly to draw diagrams
```

## Rules

- **Ambiguity is exit 3** with candidates one per line (`note path/show`, kanban card
  matches, `tasks done`, base names). Re-run with the exact match — never guess.
- **Never hand-edit `.kanban` or `.base` files.** One missing field makes the whole file
  unloadable in the app. tess validates and writes atomically; it also refuses to clobber
  a board the app just saved — if it says the file changed, re-run.
- Vault app open with the same board on screen? Prefer telling the user, or touch a board
  the app isn't displaying.
- Everything degrades: a plain folder of .md with no `.lokus/`, no hub, no boards works —
  commands explain what's absent instead of erroring. Don't treat that as failure.
- Wiki-link liberally in bodies you write: `[[Note Name]]` — the vault's graph and
  backlinks come from these.
- Read on demand; never bulk-load the vault into context.
