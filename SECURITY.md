# Security

## Reporting

Report vulnerabilities privately via [GitHub security advisories](https://github.com/cleanmcp/tess/security/advisories/new) — please don't open a public issue for anything exploitable. You'll get a response within a few days.

## Scope notes (how tess touches your data)

- The optional **life** layer reads your Mac's own local stores (Messages, Mail, Contacts, Calendar, Books, Music) — always **read-only sqlite** opened with `mode=ro`; mutations (send, reply, flag…) go through the official apps via AppleScript and always confirm with a human first. Nothing is uploaded anywhere by tess itself.
- The **brain** layer only touches the markdown folder you point `TESS_VAULT` at.
- The **fleet** layer drives locally-running agent CLIs (claude/kimi via hcom); spend caps and deploy deny-lists are enforced at spawn.
- `tess update` is a `git pull --ff-only` of this repo; it never touches `~/.config/tess/`.

Anything that violates the above — a write to a store that should be read-only, data leaving the machine, a permission prompt tess triggers without saying so — is a bug worth reporting even if it isn't exploitable.
