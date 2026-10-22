#!/usr/bin/env bash
# tess help <command> — detailed help for a single command (usage + example).
# `tess help` with no arg shows the full menu (handled in tess).
c="${1:-}"; c="${c#tess }"
B=$'\033[1m'; C=$'\033[36m'; D=$'\033[2m'; R=$'\033[0m'; [ -t 1 ] || { B=; C=; D=; R=; }
h() { printf "%s%s%s\n" "$C" "$1" "$R"; shift; for l in "$@"; do printf "  %s\n" "$l"; done; echo; }

case "$c" in
  new|worktree) h "tess new [<repo>] <feature> [--repo a,b] [--fleet|--all] [--base <branch>] [--on <peer>]" \
    "Create feature worktrees (+ .env files copied in; opens in cmux if installed). Deterministic grammar:" \
    "  tess new <feature>         -> pick a repo (interactive) or the repo you're in; --fleet for TESS_REPOS" \
    "  tess new <repo> <feature>  -> that repo by NAME (see tess repos) — an unknown repo is an ERROR, never reinterpreted" \
    "  --repo a,b explicit set · --fleet/--all use TESS_REPOS / TESS_REPOS_ALL from ~/.config/tess/config (opt-in, never hardcoded)" \
    "Several copies of a repo name? The one you actually use wins (zoxide + git activity; a genuine tie shows a picker)." \
    "  --on <peer> cuts it on ANOTHER machine, via that machine's own tess, then installs dependencies there so it is runnable on arrival" \
    "Feature names are flat (letters, digits, . _ -) — a branch-style name like fix/thing is not a feature name." \
    "Single-repo features have no folder shell: tess path <feature> (and spawned agents) land INSIDE the repo." \
    "${D}e.g. tess new redis-cache · tess new lokus fix-toolbar · tess new hotfix-login --base develop${R}" ;;
  repos)     h "tess repos [index|find <name>|pick <name>]" \
    "The repo map: every git repo on disk, ranked by use (zoxide + git activity). Refreshes daily." \
    "Permission-safe on macOS: never triggers TCC dialogs — without Full Disk Access it skips" \
    "Desktop/Documents/Downloads instead of prompting (add roots via TESS_REPO_DIRS)." ;;
  ls|list)   h "tess ls" "List your feature worktree folders." ;;
  rm|remove) h "tess rm <feature>" "Tear down a feature's worktrees (the clean way). Branches stay (delete merged ones: tess branches)." ;;
  done)      h "tess done <feature> [--dry-run] [--yes]" \
    "One-shot teardown: kill the feature's agents (their panes close), remove its worktrees, sweep the folder." \
    "Only agents working INSIDE that feature dir are touched. Warns about uncommitted changes." \
    "${D}e.g. tess done redis-cache --dry-run${R}" ;;
  env)       h "tess env <feature>" "Re-copy .env files into a feature — each worktree's own source repo is found via its gitdir pointer, so ANY repo works (not just the fleet)." ;;
  clean)     h "tess clean" "Prune stale worktree registrations (after you delete folders by hand)." ;;
  branches)  h "tess branches" "List branches already merged into \$TESS_MAIN_BRANCH and offer to delete them." ;;
  path)      h "tess path <feature> [repo]" \
    "Print a worktree's path — for agents: cd \"\$(tess path <feature> <repo>)\"." \
    "A single-repo feature returns the repo dir itself, so you always land inside a git repo." ;;
  wt)        h "tess wt" "Worktree status: every feature, its repos, branch, dirty count, and source repo." ;;

  todo|todos) h "tess todo   ·   tess todo add [-p <project>] <text>   ·   tess todo start|done <id>   ·   tess todo board" \
    "A persistent coding checklist shared across sessions (markdown checkboxes in ~/.config/tess/state/todos.md)." \
    "Open items are injected at the top of every new agent session (a SessionStart hook running 'tess todo --hook'), so work survives the session that created it." \
    "Subcommands: (bare)=list open · add · start <id> (mark in progress, [/]) · done <id…> · board (kanban view) · reopen <id> · rm <id> · clear (drop completed) · all · edit." \
    "${D}e.g. tess todo add -p api \"add retries to the sync job\" · tess todo board${R}" ;;

  claude|kimi) h "tess claude|kimi [feat|.] [\"prompt\"] [--model M] [--effort E] [--file f]" \
    "Launch the agent. With a feature name, create/enter that worktree first ('.' = current dir, new pane)." \
    "With a prompt/model/effort, the spawner VERIFIES each actually applied (trust dialog answered, /model + /effort confirmed on screen, prompt transcript-confirmed) before handing off." \
    "Roles are ENFORCED, not suggested: --readonly (plan mode) · --auto (starts IN auto permission mode — no per-command prompts, footer-verified) · deploy commands denied unless --can-deploy · --budget N caps spend in USD." \
    "--tag T groups names (default: feat) · --no-auto-trust · --dry-run shows the plan." \
    "${D}e.g. tess kimi redis-cache \"profile the cache layer\" --model kimi-k2 --effort high${R}" \
    "${D}     tess claude . \"fix the failing test\" --model fable5${R}" ;;
  cursor) h "tess cursor [feat|.] [\"prompt\"] [--model M] [--context 272k|1m] [--effort none|low|medium|high|xhigh|max] [--fast|--no-fast]" \
    "Launch Cursor Agent (the \`agent\` CLI via hcom). Model customizations match the Cursor UI:" \
    "  --model slug (composer-2.5, gpt-5.6-sol, claude-opus-5-thinking-max, …)" \
    "  --context 272k|1m   Context window" \
    "  --effort none|low|medium|high|xhigh|max   Reasoning depth" \
    "  --fast / --no-fast   Fast mode toggle" \
    "These compose into one --model string: slug[context=1m,reasoning=max,fast=false] (--effort → reasoning=)." \
    "--readonly (--plan) · --auto (--force) · --trust (default on feature spawns) · --dry-run." \
    "${D}e.g. tess cursor mail-fix \"clean inbox\" --model gpt-5.6-sol --context 1m --effort max${R}" \
    "${D}     tess cursor . --model composer-2.5 --fast${R}" ;;
  resume|r)  h "tess resume [--plain] [--refresh]" \
    "Pick from ALL past Claude/Kimi/Cursor sessions (any folder) and resume in the session's own folder (recreated if deleted — sessions are keyed to it)." \
    "Each row gets a one-line AI summary of what the session worked on (local model, cached — instant after first run)." \
    "--plain = raw titles, no AI · --refresh = regenerate summaries · ✗dir marks sessions whose folder is gone." ;;
  handoff)   h "tess handoff [<peer>|back] [--pick] [--session <id>] [--no-setup] [--dry-run]" \
    "Move a live session — context, folder, and uncommitted work — to another machine, and bring it back. One command: nothing to set up by hand on arrival." \
    "A baton, not a mirror: one machine holds a session at a time, so there is never anything to merge." \
    "Code travels as a throwaway WIP commit pushed over ssh (delta only, soft-reset on arrival); .env files rsync beside it; the transcript is rewritten for the peer's home directory." \
    "Dependencies never travel — they are gigabytes of platform-specific output — so the peer installs its own, detected from the lockfile (--no-setup skips it; TESS_HANDOFF_SETUP sets the command)." \
    "Anything uncommitted found on the peer is committed to a rescue ref first and the hash printed, so nothing there is lost." \
    "Bare 'tess handoff' shows what is parked where. Peers: TESS_PEERS=\"mini=<ssh target>\" in ~/.config/tess/config." ;;
  tunnel)    h "tess tunnel <peer> <port>… [--login] [--bg] · --list · --stop" \
    "Forward a peer's localhost to this machine: its 127.0.0.1:<port> shows up as your localhost:<port>." \
    "Use it to open a dev server an agent started on another machine, without binding that server to the network." \
    "--login forwards the ports agent CLI sign-ins redirect to, so a sign-in started over ssh can finish in the browser here." \
    "<local>:<remote> picks a different local port · --bg detaches (--list shows them, --stop closes them)." ;;
  think|partner) h "tess think" "Thinking-partner mode: loads your company context, sounding-board (not idea-firehose), researches in the background." ;;
  post|brand|write) h "tess post" "Daily content partner for your personal brand. Learns your taste each session." ;;
  local|offline|small|big|med|medium) h "tess local | small | big [prompt]" \
    "Offline AI via a local model (ollama). small=fast, big=best. Configure tiers in ~/.config/tess/models." ;;
  ask)       h "tess ask \"<question>\"" "Say what you want in plain words; it routes to the right command or answers, and speaks it." ;;
  listen)    h "tess listen" "Hands-free: say \"tess, <what you want>\". Uses whisper + local model. Ctrl+C to stop." ;;
  voice)     h "tess voice" "Type/dictate loop (pairs with Wispr Flow)." ;;
  agents)    h "tess agents [--json]" "Live dashboard of running AI agents. --json = machine-readable (same as tess status --json)." ;;
  status)    h "tess status [--json]" \
    "Fleet at a glance: every agent's state (BLOCKED first), age, worktree, unread count, current activity." ;;
  diff)      h "tess diff <agent|feature> [--full]" \
    "What an agent/feature has actually changed: per-worktree dirty files + diffstat (--full = whole diff)." ;;
  approve)   h "tess approve <agent> [--option N]" \
    "Answer a BLOCKED agent's approval dialog: shows the dialog, accepts the highlighted option (or types option N first), confirms it unblocked." ;;
  hcom)      h "tess hcom <anything>" "Raw fleet-comms passthrough (power users / agents) — the low-level layer tess drives for you. You never need this directly; every fleet action has a first-class tess command (agents, status, tell, inject, report …)." ;;
  tell)      h "tess tell <agent|feature|all> [--intent request|inform|ack] [--raw] -- <msg>" \
    "Speak as @bigboss. A FEATURE name messages all its agents; 'all' broadcasts." \
    "@words inside the message that collide with live agent names are invisibly escaped so nobody gets accidentally DM'd (emails/handles arrive intact). --raw disables that." ;;
  ship)      h "tess ship <feature> [--merge] [--dry-run]" \
    "Collect and ship a finished feature, per repo: diff vs $TESS_MAIN_BRANCH → tests (TESS_TEST_CMD) → push → PR (gh) → --merge squash-merges." \
    "Uncommitted changes block that repo. Afterwards: tess done <feature> --yes." ;;
  spend)     h "tess spend" \
    "Budget ledger: every agent spawned with --budget/--readonly, its cap and model. Caps are ENFORCED at spawn (claude --max-budget-usd)." ;;
  orchestrate|orch) h "tess orchestrate \"<goal>\" [--model M] [--effort E] [--dry-run]   ·   tess orchestrate off" \
    "Hire an AI lead: it decomposes the goal, spawns/steers sub-agents (tess team), receives all watch escalations, verifies, and reports to @bigboss." \
    "'off' hands the lead role (escalations) back to you; agents keep running." ;;
  team)      h "tess team <spec.yaml|-> [--dry-run] [--parallel]" \
    "Fan out a whole fleet in one command: each agent gets its own worktree, prompt, model, effort and role template (defaults + per-agent overrides in the YAML)." \
    "Templates: investigate / implement / review (built-in) + your own in ~/.config/tess/templates/. count: N clones an agent." \
    "Every spawn is VERIFIED (trust answered, model+effort confirmed, prompt landed). --dry-run prints the exact plan." \
    "${D}e.g. tess team fleet.yaml --dry-run   ·   cat spec.yaml | tess team -${R}" ;;
  wait)      h "tess wait <agent|feature|all> [--timeout N]" \
    "Block until the target(s) stop working. Exit 0 = idle/finished, 2 = BLOCKED on approval, 3 = timeout, 4 = died." ;;
  watch)     h "tess watch [on|off|status] [--phone] [--once] [--interval N]" \
    "The escalation loop (F6): the MOMENT any agent goes BLOCKED / DIES / sits IDLE >20s it pings the lead —" \
    "a DM to the lead identity (default @bigboss → shows in tess inbox; tess orchestrate registers its own lead agent) and, with --phone + TESS_NOTIFY_CONTACT in config, your iPhone via iMessage." \
    "'on' runs it in the background (nohup), 'off' stops it, bare = foreground, --once = single scan (cron-able)." ;;
  inbox)     h "tess inbox [--all|--peek|--json]" \
    "Your unread mail as the lead: @bigboss mentions + agent reports (broadcasts), full text." \
    "Reading marks them read (cursor in ~/.config/tess/state). --peek doesn't; --all shows history." ;;
  report)    h "tess report <agent> [--n N] [--json]" \
    "The agent's FULL last message (no truncation), plain text — scriptable. --n 3 for the last 3 exchanges." ;;
  digest)    h "tess digest [--json]" \
    "One merged summary of every running agent: state, worktree, current task, last report snippet." \
    "${D}the lead's 10-second fleet overview — pair with tess report <agent> to zoom in${R}" ;;
  kill)      h "tess kill <agent|feature|tag:X|all>" \
    "Kill an agent (closes its pane). A FEATURE name kills only that feature's agents and keeps the worktree (full teardown: tess done)." ;;
  inject)    h "tess inject <agent> [--timeout N] [--retries N] [--force] -- <text>" \
    "Reliably type a prompt into a running agent's terminal: waits until its input is READY, submits, then CONFIRMS the turn landed (retries if not). Raw terminal injection silently drops keys while an agent is busy — this never does." \
    "Refuses if the agent is blocked on an approval dialog (use tess approve) or has a draft in its box (--force)." \
    "${D}e.g. tess inject keto -- status report please${R}" ;;
  loop)      h "tess loop <claude|kimi> \"<goal>\" [max-rounds]" \
    "Autonomous manager->worker loop: a manager agent plays YOU, reviews the worker's last report, and issues the next instruction until the goal is DONE." \
    "Runs headless with tools + skipped permissions, in the current folder. Ctrl+C stops. Transcript saved to ~/.local/share/tess-loop/." \
    "${D}e.g. tess loop claude \"add tests for the auth module and make them pass\"${R}" ;;

  people|companies) h "tess people | companies" "Roster of your contacts / companies (from note tags + folders)." ;;
  reminders|followups) h "tess reminders" \
    "Open follow-ups — every open checkbox across your vault (all states: [ ] [/] [!] [?] [>])." \
    "The richer face is tess tasks: scoped scans, --json, and 'tess tasks done <match>' to check off." ;;
  vault)     h "tess vault [map|folders|mkdir <rel/path>|init <dir>] [--json]" \
    "Your knowledge base, oriented. Bare = the map: folders + note counts, kanban boards, bases," \
    "templates, canvases — and the 'write here when unsure' default for new notes." \
    "  folders = flat folder list · mkdir = new folder inside the vault (safe: no escapes/dotfolders)" \
    "  init <dir> = scaffold a NEW workspace anywhere (.lokus/ + notes/ + Tasks.kanban — Lokus opens it natively)" \
    "Works on any markdown folder (Obsidian, plain files); Lokus extras light up when present." \
    "${D}e.g. tess vault · tess vault folders --json · tess vault init ~/Notes${R}" ;;
  note|notes) h "tess note new <name> [--in <folder>] [--template <t>] [--tags a,b] [-- body]   ·   note ls|path|show" \
    "Create + find notes properly. 'new' writes frontmatter (title/tags/created) into the right folder" \
    "(default: the hub Inbox, else the vault root — see 'tess vault'). --template renders {{date}}/{{title}}/…" \
    "  ls [folder]  newest notes · path <name>  resolve to a file path · show <name>  print one (the read" \
    "  escape hatch when a note's name collides with a tess command). Ambiguous name = exit 3 + candidates." \
    "${D}e.g. tess note new \"competitor teardown\" --in research --tags intel${R}" ;;
  kanban)    h "tess kanban [board]   ·   kanban add [board] <title>   ·   move|done|rm <card>   ·   new <name>" \
    "Kanban boards as .kanban files (Lokus-native JSON — the app loads what tess writes, and vice versa)." \
    "Bare = render the board (or list them all). Cards match by id prefix or title substring;" \
    "ambiguous = exit 3 + candidates. Writes are atomic and refuse to clobber a board an open app just saved." \
    "Flags: --board <b> to disambiguate · --col/--desc/--due/--priority/--tags/--note on add · --json." \
    "${D}e.g. tess kanban add \"ship the deck\" --col \"In Progress\" · tess kanban done deck${R}" ;;
  tasks)     h "tess tasks [folder|note] [--all] [--json]   ·   tess tasks done <match> [--in <scope>]" \
    "Every checkbox across your notes, all states: [ ] todo · [/] in progress · [!] urgent · [?] question ·" \
    "[>] delegated · [-] cancelled · [x] done (done/cancelled hidden unless --all)." \
    "'done <match>' checks off the matching open task in its source file (ambiguous = exit 3 + candidates)." \
    "${D}e.g. tess tasks 06-Network · tess tasks done \"follow up with sam\"${R}" ;;
  base|bases) h "tess base query [--from <folder>] [--where \"k<op>v\"]… [--sort k[:desc]] [--cols a,b]   ·   tess bases · base <name>" \
    "Query notes like a database over their frontmatter + file stats (name/title/path/created/modified/size)." \
    "Ops: = contains · == exact · != > >= < <= · \"k is-empty\" / \"k is-not-empty\" — quote every --where." \
    "'tess bases' lists saved Lokus base views (.lokus/bases/*.base); 'tess base <name>' runs one." \
    "${D}e.g. tess base query --where \"tags=person\" --sort modified:desc --cols title,path${R}" ;;
  links)     h "tess links <note> [--json]   ·   tess links --broken" \
    "The wiki-link graph: outlinks (resolved + unresolved) and backlinks for a note — aliases, headings," \
    "embeds all count. --broken = every [[link]] in the vault that resolves to nothing, by source note." \
    "${D}e.g. tess links \"Sam Altman\" · tess links --broken${R}" ;;
  canvas)    h "tess canvas [new <name> [--in <folder>]]" \
    "Excalidraw canvases in your vault. Bare = list; new = create an empty app-valid .excalidraw." \
    "It's plain Excalidraw JSON — agents can write elements directly to draw diagrams; opens in Lokus or excalidraw.com." ;;
  person|company) h "tess person|company <name> -- <desc>" "Create a tagged contact/company note (shows in the roster)." ;;
  add)       h "tess add <name> -- <text>" "Append a line to a note (creates it if new)." ;;
  log)       h "tess log -- <text>" "Quick timestamped capture to your log note." ;;
  brief)     h "tess brief" "Show your NOW note — what's going on right now." ;;
  commands|custom) h "tess commands [new <name>]" \
    "Your custom commands live in ~/.config/tess/commands/ and survive updates." \
    "tess commands new <name>   scaffold one, then run it as: tess <name>" ;;

  messages|msg) h "tess messages [who]" "Recent iMessages/SMS incl. group chats. Search by contact name, group, or text." ;;
  chat|thread)  h "tess chat <name|group>" "Full conversation thread with someone (or a group), with inline images (terminals with image support)." ;;
  send|text)    h "tess send <name> -- <message>" \
    "Send an iMessage. Ambiguous names show a picker (or, for agents, error with options)." "${D}e.g. tess send mom -- on my way${R}" ;;
  calls)     h "tess calls" "Recent call log with contact names." ;;
  mail|email) h "tess mail [query] · from <who> · read <id> · search <text>  +  actions" \
    "Email via the local Apple Mail store. READS are sqlite-fast and never touch the store:" \
    "  bare/query = newest mail (spam+trash hidden unless queried) · read <id> = full body · search = subjects+bodies." \
    "ACTIONS go through Mail.app (AppleScript): send <who> -- \"<subj>\" \"<body>\" · reply <id> [--all] -- \"<text>\" ·" \
    "  mark <id> read|unread · flag <id> [red|orange|yellow|green|blue|purple|gray|off] · archive <id> ·" \
    "  move <id> <mailbox> (tess mail boxes lists them) · delete <id>." \
    "send/reply/delete ALWAYS need a human. At a terminal that's the [y/N]; away from one it's a" \
    "  SEND WINDOW you opened yourself: ${B}tess mail grant${R} [--reply|--send|--delete] [--minutes N] [--uses N]" \
    "  — short-lived, use-capped, scoped, logged to ~/.config/tess/mail-sent.log. Default 30 min / 3 uses / reply." \
    "  ${B}tess mail grants${R} shows what's open · ${B}tess mail revoke${R} closes it now. With no window, agent calls" \
    "  still just get the exact command handed back. grant/grants/revoke need NO Full Disk Access." \
    "Flags: --limit N · --json · --from <acct> (default From: \$TESS_MAIL_FROM in ~/.config/tess/config)." \
    "${D}e.g. tess mail from alex · tess mail search \"pitch deck\" · tess mail send sam -- \"Deck\" \"attached soon\"${R}" ;;
  calendar|cal) h "tess calendar [days]" "Upcoming events (incl. recurring). Default 7 days." ;;
  read|book) h "tess read [title]" "Reading companion for your current Apple Book: recap + gist for your page, explains anything, takes notes." ;;
  music)     h "tess music [<song>|play|pause|next|prev|search <q>]  +  library engine" \
    "Apple Music: now-playing with art, fuzzy-play your library, catalog search — plus query the whole library:" \
    "  lib [text] [filters] = any slice · top/recent [N] · loved · artists/albums/genres/years [--by tracks|plays|time] ·" \
    "  stats · playlists · love/unlove [q|id:N] · rate [q|id:N] <0-5>  (no target = current track)." \
    "Flags: --sort <field> [--asc|--desc] · --filter \"f<op>v\" (repeatable; bare artist=drake works) · --limit N ·" \
    "  --cols a,b,c · --ids 12,34 (hand-picked set, order kept) · --json · --fresh (skip cache) ·" \
    "  --play (play/queue results) · --to-playlist <name> (materialize a real playlist)." \
    "Fields: name artist album albumartist genre year duration plays played added rating loved size id." \
    "Ops: = contains · == exact · != · > >= < <=  — dates take 2024-06-01 | 30d/12w/6m/1y · rating in stars 0-5." \
    "${D}e.g. tess music lib --filter \"added=90d\" --sort plays · tess music lib rap \"year>=2020\" --to-playlist \"new rap\"${R}" ;;

  open|app|launch) h "tess open <app>  (or just: tess <app>)" "Open any installed app by name (fuzzy)." ;;
  apps)      h "tess apps" "Fuzzy-pick an app to open." ;;
  login)     h "tess login [rm|add \"<name>\"]" "See/edit what opens at login. 'rm' stops an app from auto-launching." ;;
  startup)   h "tess startup [install|uninstall]" \
    "Open your startup set (TESS_STARTUP_OPEN) + quit the flood (TESS_STARTUP_QUIT). 'install' runs it at login." ;;

  doctor)    h "tess doctor" "Quick Mac health check: open-file limit, worktree count, local model." ;;
  fix-files|fixfiles) h "tess fix-files" "Permanently raise the macOS open-file limit (asks for your password)." ;;
  disk)      h "tess disk" "Disk usage of your worktrees (slow on big node_modules)." ;;
  version|--version) h "tess --version" "Print the tess version and the commit it's running from." ;;
  uninstall) h "./uninstall.sh [--yes]" \
    "Remove what install.sh added: unwires your AI agents (skills, hooks, primers), removes the tess command, and offers to delete ~/.config/tess." \
    "NEVER touches your source repos, your feature worktrees, or your notes vault — it prints where they are and leaves them alone." ;;
  update)    h "tess update" "Pull the latest tess now. (It also auto-pulls in the background on any command.)" ;;
  wire)      h "tess wire [--dry-run] [--undo]" \
    "Teach every AI coding agent on this machine about tess. Three layers:" \
    "  skills  — portable SKILL.md linked into every skills root found (Claude Code, Cursor, Codex, Gemini, opencode). Loads on demand; costs nothing until relevant." \
    "  hooks   — a guard that BLOCKS raw 'git worktree add/remove/move' and redirects to 'tess new' (Claude Code + Cursor). Bypass once with TESS_ALLOW_RAW_GIT=1." \
    "  primer  — agent-primer.md injected into CLAUDE.md / AGENTS.md / GEMINI.md for agents without skill support." \
    "Idempotent — re-run after any update. Symlinks, not copies, so 'tess update' refreshes every agent for free. --dry-run shows the plan; --undo removes everything." ;;
  cheat)     h "tess cheat" "Open the full cheatsheet." ;;

  help) h "tess help <command>" "Detailed help for one command. Every subcommand also takes --help/-h directly (always safe — never creates or spawns anything)." ;;
  "" ) echo "usage: tess help <command>   (or just 'tess' for the full menu)" ;;
  * ) echo "no help for '$c'. Run 'tess' for the full list, or 'tess help <command>'." ;;
esac
