# tess branding pass — hcom leaks rebranded

**Rule:** the client should never see the backend ("hcom") in anything tess shows them. Backend/server plumbing stays hcom; only the **client-facing surface** is rebranded. All changes are cosmetic on output — the passthrough and update mechanism still work, no backend calls renamed.

## Leaks found + how they were fixed

| # | Leak (what the user saw) | Where | Fix |
|---|---|---|---|
| 1 | `→ hcom vX.YZ available — run \`hcom update\`` nag banner printed to stderr on invocation | backend, surfaced by every `tess` cmd that shells out (`tess hcom`, `tess agents`, `tess kill`, spawn fallback) | New `_hcom()` wrapper in `bin/tess` filters that one banner line from stderr; the 4 `exec $HCOM …` sites route through it. Also scrubbed from captured stderr in the Python `hcom()` wrapper so surfaced errors can't leak it. Update mechanism untouched. |
| 2 | `[uvx hcom:<name>]` tracking marker agents echo in their first reply, shown in `tess report` / `tess digest` / `tess inbox` | rendered transcript/message text | New `scrub()` helper (`_tess_agents.py`) strips the marker; applied at every render point (report action, digest last/task, inbox text). |
| 3 | `tess hcom <anything>` advertised in the main menu | `bin/tess` menu | Removed from the menu (the `tess hcom` command still works — it's now an unadvertised power-user/agent escape hatch). |
| 4 | Raw backend activity shown verbatim in `tess status` / `tess digest` (e.g. an agent running `uvx hcom send @bigboss …`) | status/digest `detail` field | New `brand()` helper rebrands the backend token → `tess` **only** on short activity/detail strings (never on prose). |
| 5 | `hcom` named in help text | `_tess-help.sh` — `agents`, `watch`, `inject` entries, and the `hcom` entry itself | Dropped `(hcom)` from `agents`; "hcom DM" → "a DM" in `watch`; "Raw 'hcom term inject'" → "Raw terminal injection" in `inject`; the `hcom` help entry reworded to describe it as the low-level passthrough without branding hcom as a product. |
| 6 | `hcom` in error messages / hints | `_tess_agents.py`, `_tess-spawn.py`, `_tess-hq.py`, `_tess-watch.py` | "hcom launch failed" → "agent launch failed"; "register with hcom" → "register with the fleet"; `check the pane (hcom term …)` → `(tess agents)`; approve hint `tess hcom term …` → `tess agents`; DIED escalation `tess hcom r <name>` → `tess resume — pick <name>`. |

## Deliberate boundary (not rebranded)
- **Agent-authored report prose** in `tess report` / `tess digest` / `tess inbox` that literally contains the word "hcom" (e.g. an agent wrote "send the hcom summary"). This is the agent's own content, not tess chrome — blanket word-replacement would corrupt reports (a report *about* rebranding hcom→tess would become gibberish). `scrub()` removes only noise (banner + marker) from prose; it never rewrites meaning. This prose stems from the agent-facing framing, which the task scoped as fine for agents.
- **`agent-primer.md` / `templates/*.md` / `README.md`** — agent-facing framing and repo attribution, explicitly out of scope.
- **Internal/comment/`TESS_RESERVED` references** — not user-facing.

## Functionality verified (post-change)
- `tess hcom list` — passthrough works, banner gone.
- `_hcom` wrapper: banner stripped, stdout intact, exit code preserved (0 on success, 7 on failure).
- `tess report <agent>` — `[uvx hcom:…]` marker gone (0 occurrences).
- `tess status`, `tess agents --json`, `tess inbox --peek`, `tess digest`, `tess watch status`, `tess tell`, `tess inject`, `tess help hcom` — all run clean.
- `scrub()` / `brand()` unit-checked; bash + python syntax-checked on all 7 files.
- No user-facing "hcom" left in tess's own output strings (grep sweep clean).
