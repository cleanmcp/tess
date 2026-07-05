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

  claude|kimi) h "tess claude|kimi [feat|.] [\"prompt\"] [--model M] [--effort E] [--file f]" \
    "Launch the agent. With a feature name, create/enter that worktree first ('.' = current dir, new pane)." \
    "With a prompt/model/effort, the spawner VERIFIES each actually applied (trust dialog answered, /model + /effort confirmed on screen, prompt transcript-confirmed) before handing off." \
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
  agents)    h "tess agents" "Dashboard of running AI agents (hcom)." ;;
  hcom)      h "tess hcom <anything>" "Full hcom CLI under tess — e.g. tess hcom list -v · tess hcom events --last 5. You never need to install or call hcom directly." ;;
  kill)      h "tess kill <agent|feature|tag:X|all>" \
    "Kill an agent (closes its pane). A FEATURE name kills only that feature's agents and keeps the worktree (full teardown: tess done)." ;;
  inject)    h "tess inject <agent> [--timeout N] [--retries N] [--force] -- <text>" \
    "Reliably type a prompt into a running agent's terminal: waits until its input is READY, submits, then CONFIRMS the turn landed (retries if not). Raw 'hcom term inject' silently drops keys while an agent is busy — this never does." \
    "Refuses if the agent is blocked on an approval dialog (use tess approve) or has a draft in its box (--force)." \
    "${D}e.g. tess inject keto -- status report please${R}" ;;
  loop)      h "tess loop <claude|kimi> \"<goal>\" [max-rounds]" \
    "Autonomous manager->worker loop: a manager agent plays YOU, reviews the worker's last report, and issues the next instruction until the goal is DONE." \
    "Runs headless with tools + skipped permissions, in the current folder. Ctrl+C stops. Transcript saved to ~/.local/share/tess-loop/." \
    "${D}e.g. tess loop claude \"add tests for the auth module and make them pass\"${R}" ;;

  people|companies) h "tess people | companies" "Roster of your contacts / companies (from note tags + folders)." ;;
  reminders|todos|followups) h "tess reminders" "Open follow-ups — every unchecked '- [ ]' item across your vault." ;;
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
