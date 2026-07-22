# Progress log — tess mail cleanup tools

## 2026-07-12
- Read existing `bin/_tess-mail.py` end-to-end.
- Searched user's live mail to identify noisy categories and counts.
- Pulled origin/main into `tess-mail` branch (already up to date).
- Created `task_plan.md`, `findings.md`, `progress.md`.
- Implemented:
  - `tess mail boxes create <name> [--account <acct>]`
  - `tess mail bulk-archive|bulk-delete|bulk-move from <who> | search <text> [mailbox]`
  - `tess mail clean [--archive <cats>] [--delete <cats>] [--all]`
- Added fast sender-pattern AppleScript path for `from` queries.
- Updated help text in `bin/_tess-help.sh`.
- Created labels under `pratham@tryclean.ai`: Promos, Social, Newsletters, Admin, DevOps.
- Archived major noisy senders (reversible):
  - Myprotein, Instagram, Career Brew, Ford from Runway, Google Scholar
  - Chipotle, The Airtable Team, Neon Changelog, PDQ Team, Railway
  - Amazon Prime Day, Amazon Business, noreply-dmarc (DMARC reports)
  - LinkedIn, Folk, Apollo, TikTok
- Moved Discover Card transaction alerts/statements back to INBOX after accidental bulk archive.
- Deleted 50 Vercel bot-deployment emails (subject contains "studilanjutid") via direct AppleScript after user said "don't stop".
- Fixed `cmd_clean` to call `bulk_action_by_mid` instead of the removed `bulk_action`.
- Re-running `tess mail clean --archive promos,social,newsletters,admin --limit 10000` in background.
- Final dry-run still shows ~1300 cleanup-category messages in the 5000 newest scan because older mail keeps surfacing as newer mail is archived; additional passes or deeper scans would be needed for a full cleanup.
