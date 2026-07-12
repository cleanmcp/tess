#!/usr/bin/env bash
# tess help <command> — detailed help for a single command (usage + example).
# `tess help` with no arg shows the full menu (handled in tess).
c="${1:-}"; c="${c#tess }"
B=$'\033[1m'; C=$'\033[36m'; D=$'\033[2m'; R=$'\033[0m'; [ -t 1 ] || { B=; C=; D=; R=; }
h() { printf "%s%s%s\n" "$C" "$1" "$R"; shift; for l in "$@"; do printf "  %s\n" "$l"; done; echo; }

case "$c" in
  new|worktree) h "tess new <feature> [base]" \
    "Create a git worktree for the feature across every configured repo, copy .env files in, open it in cmux." \
    "tess new --all <feature>   also include optional repos (TESS_REPOS_ALL)." \
    "${D}e.g. tess new redis-cache${R}" ;;
  ls|list)   h "tess ls" "List your feature worktree folders." ;;
  rm|remove) h "tess rm <feature>" "Tear down a feature's worktrees (the clean way). Offers to delete the branch." ;;
  done)      h "tess done <feature> [--dry-run] [--yes]" \
    "One-shot teardown: kill the feature's agents (their panes close), remove its worktrees, sweep the folder." \
    "Only agents working INSIDE that feature dir are touched. Warns about uncommitted changes." \
    "${D}e.g. tess done redis-cache --dry-run${R}" ;;
  env)       h "tess env <feature>" "Re-copy .env files from the source repos into an existing feature worktree." ;;
  clean)     h "tess clean" "Prune stale worktree registrations (after you delete folders by hand)." ;;
  branches)  h "tess branches" "List branches already merged into \$TESS_MAIN_BRANCH and offer to delete them." ;;
  path)      h "tess path <feature> [repo]" "Print a worktree's path — for agents: cd \"\$(tess path <feature> <repo>)\"." ;;
  wt)        h "tess wt" "Full git worktree status across all repos." ;;

  todo|todos) h "tess todo   ·   tess todo add [-p <project>] <text>   ·   tess todo done <id>" \
    "A persistent coding checklist shared across sessions (markdown checkboxes in ~/.config/tess/state/todos.md)." \
    "Open items are injected at the top of every new agent session (a SessionStart hook running 'tess todo --hook'), so work survives the session that created it." \
    "Subcommands: (bare)=list open · add · done <id…> · reopen <id> · rm <id> · clear (drop completed) · all · edit." \
    "${D}e.g. tess todo add -p api \"wire the interpreter into runLeadgen\"${R}" ;;

  claude|kimi) h "tess claude|kimi [feat|.] [\"prompt\"] [--model M] [--effort E] [--file f]" \
    "Launch the agent. With a feature name, create/enter that worktree first ('.' = current dir, new pane)." \
    "With a prompt/model/effort, the spawner VERIFIES each actually applied (trust dialog answered, /model + /effort confirmed on screen, prompt transcript-confirmed) before handing off." \
    "Roles are ENFORCED, not suggested: --readonly (plan mode) · --auto (starts IN auto permission mode — no per-command prompts, footer-verified) · deploy commands denied unless --can-deploy · --budget N caps spend in USD." \
    "--tag T groups names (default: feat) · --no-auto-trust · --dry-run shows the plan." \
    "${D}e.g. tess kimi redis-cache \"profile the cache layer\" --model kimi-k2 --effort high${R}" \
    "${D}     tess claude . \"fix the failing test\" --model fable5${R}" ;;
  resume|r)  h "tess resume" "Pick from ALL past Claude/Kimi sessions (any folder) by AI summary; resumes it in its folder." ;;
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
  reminders|followups) h "tess reminders" "Open follow-ups — every unchecked '- [ ]' item across your vault." ;;
  person|company) h "tess person|company <name> -- <desc>" "Create a tagged contact/company note (shows in the roster)." ;;
  add)       h "tess add <name> -- <text>" "Append a line to a note (creates it if new)." ;;
  log)       h "tess log -- <text>" "Quick timestamped capture to your log note." ;;
  brief)     h "tess brief" "Show your NOW note — what's going on right now." ;;
  commands|custom) h "tess commands [new <name>]" \
    "Your custom commands live in ~/.config/tess/commands/ and survive updates." \
    "tess commands new <name>   scaffold one, then run it as: tess <name>" ;;

  messages|msg) h "tess messages [who]" "Recent iMessages/SMS incl. group chats. Search by contact name, group, or text." ;;
  chat|thread)  h "tess chat <name|group>" "Full conversation thread with someone (or a group), with inline images (in cmux)." ;;
  send|text)    h "tess send <name> -- <message>" \
    "Send an iMessage. Ambiguous names show a picker (or, for agents, error with options)." "${D}e.g. tess send mom -- on my way${R}" ;;
  calls)     h "tess calls" "Recent call log with contact names." ;;
  mail|email) h "tess mail [query] · from <who> · read <id> · search <text>  +  actions" \
    "Email via the local Apple Mail store. READS are sqlite-fast and never touch the store:" \
    "  bare/query = newest mail (spam+trash hidden unless queried) · read <id> = full body · search = subjects+bodies." \
    "ACTIONS go through Mail.app (AppleScript): send <who> -- \"<subj>\" \"<body>\" · reply <id> -- \"<text>\" ·" \
    "  mark <id> read|unread · flag <id> [red|orange|yellow|green|blue|purple|gray|off] · archive <id> ·" \
    "  move <id> <mailbox> (tess mail boxes lists them) · delete <id>." \
    "send/reply/delete ALWAYS ask a human to confirm — agent calls get the exact command to hand over instead." \
    "Flags: --limit N · --json · --from <acct> (default From: \$TESS_MAIL_FROM in ~/.config/tess/config)." \
    "${D}e.g. tess mail from yuriy · tess mail search \"pitch deck\" · tess mail send kevin -- \"Deck\" \"attached soon\"${R}" ;;
  calendar|cal) h "tess calendar [days]" "Upcoming events (incl. recurring). Default 7 days." ;;
  read|book) h "tess read [title]" "Reading companion for your current Apple Book: recap + gist for your page, explains anything, takes notes." ;;
  music)     h "tess music [play|pause|next|prev|search <q>|<song>]" \
    "Apple Music: now-playing with album art, fuzzy-play your library, or search the catalog." ;;

  open|app|launch) h "tess open <app>  (or just: tess <app>)" "Open any installed app by name (fuzzy)." ;;
  apps)      h "tess apps" "Fuzzy-pick an app to open." ;;
  login)     h "tess login [rm|add \"<name>\"]" "See/edit what opens at login. 'rm' stops an app from auto-launching." ;;
  startup)   h "tess startup [install|uninstall]" \
    "Open your startup set (TESS_STARTUP_OPEN) + quit the flood (TESS_STARTUP_QUIT). 'install' runs it at login." ;;

  doctor)    h "tess doctor" "Quick Mac health check: open-file limit, worktree count, local model." ;;
  fix-files|fixfiles) h "tess fix-files" "Permanently raise the macOS open-file limit (asks for your password)." ;;
  disk)      h "tess disk" "Disk usage of your worktrees (slow on big node_modules)." ;;
  update)    h "tess update" "Pull the latest tess now. (It also auto-pulls in the background on any command.)" ;;
  cheat)     h "tess cheat" "Open the full cheatsheet." ;;

  help) h "tess help <command>" "Detailed help for one command. Every subcommand also takes --help/-h directly (always safe — never creates or spawns anything)." ;;
  "" ) echo "usage: tess help <command>   (or just 'tess' for the full menu)" ;;
  * ) echo "no help for '$c'. Run 'tess' for the full list, or 'tess help <command>'." ;;
esac
