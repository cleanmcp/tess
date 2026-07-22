# Findings — tess mail cleanup tools

## Existing `tess mail` architecture
- File: `bin/_tess-mail.py`
- Reads from `~/Library/Mail/V*/MailData/Envelope Index` via read-only sqlite connection.
- Accounts resolved by scanning mailbox headers (`Delivered-To`, `X-Original-To`).
- Actions (`archive`, `move`, `delete`, `mark`, `flag`) use AppleScript against Mail.app.
- `delete`/`send`/`reply` use `confirm_or_die()` and bail with the exact command when non-interactive.

## Command routing
- `bin/tess` routes `mail|email` to `python3 "$TESS_BIN/_tess-mail.py" "$@"`.
- `bin/_tess-help.sh` has the help block under `mail|email)`.

## Identified noisy email categories in user's mail
- **Promos:** Myprotein, Amazon marketing, Chipotle Rewards, Airtable product blasts, OpenAI product blasts.
- **Social:** Instagram notifications (multiple accounts), LinkedIn/Facebook type blasts.
- **Newsletters:** Career Brew, Ford from Runway, Railway changelog, Neon changelog, Google Scholar alerts.
- **Admin noise:** Daily DMARC reports (`noreply-dmarc-support@google.com`), Google security alerts, Vercel blocked deployments from bot accounts (`studilanjutid-8738`), calendar accepted/declined/updated notifications.
- **DevOps (keep but maybe archive old):** Vercel alerts, Neon alerts, Railway alerts, GitHub notifications, Google Cloud alerts.
- **Business (keep):** Clean Team threads, pitch deck emails, investor intros (Crunchbase, Harmonic, Harlem Capital), Fathom recaps, Calendly business invites.
- **Personal/school (keep):** Sallie Mae (gmail), Gannon school emails.

## Risk notes
- Bulk delete is destructive. We will mirror the existing `delete` confirmation behavior.
- Heuristic categorization is imperfect; default `clean` behavior is dry-run summary.
- Mailbox creation via AppleScript needs account selection; default to `$TESS_MAIL_FROM` or most-used account.
