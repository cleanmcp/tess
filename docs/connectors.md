# Connectors

[← README](../README.md)

Everything tess reaches on your machine. **All local** — it reads your Mac's own SQLite databases and drives its own apps. Nothing is uploaded. Nothing auto-loads: a connector costs zero tokens and stays dormant until a command asks for it.

Needs macOS permissions you grant yourself: **Full Disk Access** for reads, **Automation** for sending.

| Connector | Access | Source |
|---|---|---|
| Notes vault | read + write | your markdown folder (`TESS_VAULT`) |
| Messages | read + **send** | `~/Library/Messages/chat.db` |
| Mail | read + **write** | `~/Library/Mail` |
| Calls | read | `CallHistoryDB` |
| Calendar | read | local Calendar DB |
| Music | read + **control** | Apple Music |
| Books | read | Apple Books |
| Repo map | read | your filesystem |

## Notes

Any markdown folder — Obsidian, [Lokus](https://github.com/lokus-ai/lokus), plain files.

```bash
tess <name>                    read a note (person, company, topic)
tess add <name> -- <text>      append (creates it if new)
tess people | companies | reminders
tess brief                     your "what's going on" note
tess log -- <text>             quick timestamped capture
```

The full knowledge layer — `tess vault`, `note`, `kanban`, `tasks`, `base`, `links`,
`canvas` — has its own page: **[The vault](vault.md)**.

## Messages · Calls · Calendar

```bash
tess messages [who]            recent iMessages/SMS, incl. groups
tess chat <name|group>         the full thread, with inline images
tess send "<full name>" -- "<msg>"     send (always confirmed first)
tess calls                     recent call log
tess calendar [days]           what's coming up
```

`tess send` needs the **full** name inline. An ambiguous name exits with the options rather than guessing.

## Mail

13 subcommands, multi-account.

```bash
tess mail [query]                        your inbox
tess mail read <id>                      full message
tess mail search <text>                  full-text
tess mail from <name|address>            everything from one person
tess mail send <who> -- "<subj>" "<body>"
tess mail reply <id> -- "<text>"
tess mail flag|mark|unread|archive|move|delete <id>
tess mail boxes                          list mailboxes
```

Sends and replies are confirmed before they go.

## Music

Not a play button — a library query engine over 15 fields.

```bash
tess music                     now playing + album art, then fuzzy-pick
tess music play <query>        fuzzy-play from library (id:<n> is exact)
tess music search <query>      search the Apple Music catalog → pick → play
tess music pause | next | prev | stop

tess music lib --filter "plays>=10" --sort plays --limit 20 --to-playlist "Heavy Rotation"
tess music top | recent | loved | playlists | stats
tess music artists | albums | genres | years [--by tracks|plays|time]
tess music love | unlove | rate id:1505 4.5
tess music cover "Late Nights" art.png
```

**Fields:** `name artist album albumartist genre year duration plays played added rating loved size id inlib`
**Filters:** `=` contains · `==` exact · `!=` · `>` `>=` `<` `<=` — quote them: `--filter "plays>=10"`

## Books

```bash
tess read [title]              reading companion for your current book, at your position
```

## Natural language & hands-free

```bash
tess ask "what did I talk to Sam about last week?"
tess voice        a type/dictate loop
tess listen       hands-free: say "tess, <what you want>"
```

`listen` is fully offline — sox records a silence-gated phrase, whisper.cpp transcribes, the local model routes it. Opt-in, because it costs CPU and battery.

## Agent modes

Five system prompts with your vault loaded. Override any in `~/.config/tess/modes/`.

```bash
tess think     thinking partner — sounding board, researches while it talks
tess post      content partner; learns your taste each session
tess boss      interactive orchestrator across all projects
tess read      reading companion
tess local     offline AI via ollama (also tess small / tess big)
```
