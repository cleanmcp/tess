# tess mail cleanup tools — implementation plan

**Goal:** Add bulk cleanup tools to `tess mail` so the user can categorize mail, create labels/mailboxes, archive low-value categories, and delete obvious junk.

**Approved design:** TBD — see options below.

## Context / findings

- Existing `tess mail` is in `bin/_tess-mail.py`.
- Reads Apple Mail sqlite store read-only; all mutations go through Mail.app AppleScript.
- Current actions: `send`, `reply`, `mark`, `flag`, `archive <id>`, `move <id> <mb>`, `delete <id>`.
- No bulk actions, no mailbox creation, no categorization.
- `delete` already requires human confirmation; we will keep that for bulk delete.
- Help text lives in `bin/_tess-help.sh`.

## Design options

### Option A: Heuristic `clean` command + mailbox creation
- Add `tess mail clean` → dry-run summary grouping inbox into categories (promos, social, newsletters, admin, bots, devops, business, personal, unknown).
- Add `tess mail clean --archive [cats]` and `tess mail clean --delete [cats]` to act on those groups.
- Add `tess mail boxes create <name> [--account <acct>]`.
- **Pros:** One command does categorization + archive/delete. Matches user request exactly.
- **Cons:** Heuristic categorization can misclassify; needs dry-run first.

### Option B: Bulk by-sender/search actions only
- Add `tess mail bulk-archive from <who> | search <text>`.
- Add `tess mail bulk-delete from <who> | search <text>`.
- Add `tess mail boxes create <name>`.
- **Pros:** Deterministic, simple, low risk.
- **Cons:** User still has to know what to clean; no "understand what email is for what".

### Option C: A + B
- Keep simple bulk actions for power users.
- Add `clean` for discovery and categorization.
- **Pros:** Covers every use case. Recommended.
- **Cons:** Slightly more code in one file.

**Recommendation:** Option C.

## Phases (once approved)

### Phase 1: Mailbox creation
- Files: `bin/_tess-mail.py`, `bin/_tess-help.sh`
- Add AppleScript to create a mailbox under an account.
- Add `cmd_boxes_create(name, account)`.
- Blast radius: mail command only.

### Phase 2: Bulk actions
- Files: `bin/_tess-mail.py`, `bin/_tess-help.sh`
- Add `cmd_bulk_archive(source, query)` and `cmd_bulk_delete(source, query)`.
- Support `from <who>` and `search <text>` matching.
- Collect matching rows, then act in a loop via existing `osa(ACT_SCRIPT, ...)`.
- Blast radius: mail command only.

### Phase 3: Smart `clean` command
- Files: `bin/_tess-mail.py`, `bin/_tess-help.sh`
- Add sender/subject heuristic categories.
- Dry-run summary by default; `--archive` / `--delete` with optional category list.
- Blast radius: mail command only.

### Phase 4: Verify
- Run `tess mail` help and a few read-only commands to ensure no regressions.
- Test new commands with `--limit` / dry-run first.

## Errors encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
