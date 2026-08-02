# The vault — your knowledge base

[← README](../README.md)

Point `TESS_VAULT` at any folder of markdown — Obsidian, [Lokus](https://github.com/lokus-ai/lokus),
plain files — and tess becomes the terminal (and your agents') interface to it. Everything is
**progressive enhancement**: a bare folder of `.md` works; Lokus-native extras (kanban boards,
base views, canvases) light up when present. The app never needs to be running.

```bash
# ~/.config/tess/config
TESS_VAULT="$HOME/Notes"
TESS_HUB="$TESS_VAULT/hub"     # optional: where NOW/people/quick-capture notes live
```

## Orient

```bash
tess vault              # the map: folders + note counts, boards, bases, templates,
                        # conventions — and "write here when unsure: <dir>"
tess vault folders      # flat folder list (--json everywhere for agents)
tess vault mkdir <rel/path>     # new folder inside the vault
tess vault init <dir>   # scaffold a NEW workspace anywhere: .lokus/ + notes/ + Tasks.kanban
```

`tess vault --json` exposes `default_new_note_dir` — the answer agents use when the user
didn't say where a note belongs.

## Notes

```bash
tess <name>                        # read a note by name
tess note new <name> [--in <folder>] [--template <t>] [--tags a,b] [--desc "d"] [-- body]
tess note ls [folder]              # newest first
tess note path <name>              # resolve to a file path
tess note show <name>              # print one — works even when the note's name
                                   # collides with a tess command (Tasks.md, Links.md…)
tess add <name> -- <text>          # append (creates if new) · tess log -- <text>  quick capture
```

`note new` writes the vault's frontmatter convention (title/tags/created/description) for you.
Templates are plain `.md` in any vault-root folder ending in `templates` — `{{date}}`,
`{{time}}`, `{{title}}`, `{{uuid}}`, `{{var || "fallback"}}` are rendered, unknown
placeholders stay visible.

## Kanban boards

`.kanban` files are the app's own JSON format — tess writes every field the app requires,
atomically, and refuses to clobber a file an open app just saved.

```bash
tess kanban                        # render the board (several? lists them)
tess kanban new <name> [--in <folder>]
tess kanban add [board] "title" [--col c] [--due YYYY-MM-DD] [--priority p] [--desc d] [--note <wiki target>]
tess kanban move <card> <col>      # card = id prefix or title substring
tess kanban done <card>            # → the board's done-ish column (errors if it has none)
tess kanban rm <card>
```

Ambiguous card matches exit 3 and list candidates — re-run with the id prefix.

## Tasks in notes

All of the app's checkbox states round-trip: `[ ]` todo · `[/]` in progress · `[!]` urgent ·
`[?]` question · `[>]` delegated · `[-]` cancelled · `[x]` done.

```bash
tess tasks [folder|note]           # every open checkbox, grouped by note
tess tasks --all                   # include done/cancelled
tess tasks done "<match>"          # check off in the source file (exact line, atomic)
tess reminders                     # the classic follow-ups view (same scan)
```

(Coding todos are a different thing — `tess todo` lives in `~/.config/tess/state`, not the
vault, and now has `tess todo start <id>` + `tess todo board` for a kanban view.)

## Query notes like a database

```bash
tess base query --where "tags=person" --sort modified:desc --cols title,path
tess base query --from projects --where "status==active" --where "priority>=2"
tess bases                         # saved Lokus base views (.lokus/bases/*.base)
tess base <name>                   # execute one
```

Ops: `=` contains · `==` exact · `!=` `>` `>=` `<` `<=` · `"k is-empty"` / `"k is-not-empty"`.
Quote every `--where`. Properties = frontmatter keys + file stats
(`name title path size created modified tags`).

## Links, canvases

```bash
tess links <note>                  # outlinks + backlinks ([[wiki links]], aliases, embeds)
tess links --broken                # every link that resolves to nothing
tess canvas                        # list Excalidraw canvases
tess canvas new <name>             # create an empty, app-valid .excalidraw
```

Canvases are plain [Excalidraw](https://excalidraw.com) JSON — agents can write elements
directly to produce real diagrams; the file opens in Lokus or on excalidraw.com.

## Contract (for agents)

- Exit codes: `0` ok · `1` error/no vault · `2` usage/not-found · `3` **ambiguous** —
  candidates printed one per line; re-run with the exact match.
- Every structured read (`vault`, `note ls/path`, `kanban`, `tasks`, `bases`, `base`,
  `links`, `canvas`) takes `--json`; `tess <name>` / `note show` print the raw note.
  Output is plain when piped.
- tess never writes outside the vault, into dot-folders, or over a file it couldn't parse.
