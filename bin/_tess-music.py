#!/usr/bin/env python3
"""tess music — Apple Music from the terminal: album art, fuzzy-play your library,
search the catalog. Interactive for humans, param-driven for agents.

  tess music                 now playing + art, then fuzzy-pick a library song
  tess music now             now playing + album art
  tess music play <query>    fuzzy-play a library track (no full name needed)
  tess music search <query>  search the Apple Music catalog -> pick -> play
  tess music pause|next|prev|stop|love
"""
import os, sys, json, subprocess, tempfile, shutil, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tess_common import C  # noqa: E402

TTY = sys.stdout.isatty()


def osa(script):
    try:
        return subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ""


def now():
    st = osa('tell application "Music" to player state')
    if st not in ("playing", "paused"):
        return None
    return {
        "name": osa('tell application "Music" to name of current track'),
        "artist": osa('tell application "Music" to artist of current track'),
        "album": osa('tell application "Music" to album of current track'),
        "state": st,
    }


def art_url(name, artist, size="450"):
    try:
        q = urllib.parse.quote(f"{name} {artist}")
        u = f"https://itunes.apple.com/search?term={q}&media=music&entity=song&limit=1"
        r = json.load(urllib.request.urlopen(u, timeout=8))["results"]
        if r:
            return r[0]["artworkUrl100"].replace("100x100bb", f"{size}x{size}bb")
    except Exception:
        pass
    return None


def render_art(url):
    if not (TTY and url and shutil.which("chafa")):
        return
    try:
        tmp = tempfile.mkstemp(suffix=".jpg")
        urllib.request.urlretrieve(url, tmp)
        subprocess.run(["chafa", "--size", "22x11", "--animate", "off", tmp])
    except Exception:
        pass


def card(prefix=""):
    n = now()
    if not n:
        print(f"  {C.grey}nothing playing{C.r}"); return
    icon = "▶" if n["state"] == "playing" else "⏸"
    render_art(art_url(n["name"], n["artist"]))
    print(f"  {icon} {C.bold}{n['name']}{C.r}")
    print(f"    {C.grey}{n['artist']} · {n['album']}{C.r}")


def library():
    out = osa('''set o to ""
tell application "Music"
  repeat with t in (get every track of library playlist 1)
    try
      set o to o & (name of t) & "\t" & (artist of t) & linefeed
    end try
  end repeat
end tell
return o''')
    return [l for l in out.splitlines() if l.strip()]


def play_library_line(line):
    name, _, artist = line.partition("\t")
    name = name.replace('"', '\\"'); artist = artist.replace('"', '\\"')
    osa(f'tell application "Music" to play (first track of library playlist 1 whose name is "{name}" and artist is "{artist}")')


def fzf(lines, prompt):
    if not (TTY and shutil.which("fzf")):
        return None
    p = subprocess.run(["fzf", "--prompt", prompt, "--height", "60%", "--reverse"],
                       input="\n".join(lines), capture_output=True, text=True)
    return p.stdout.strip() or None


def catalog(query, limit=15):
    q = urllib.parse.quote(query)
    u = f"https://itunes.apple.com/search?term={q}&media=music&entity=song&limit={limit}"
    try:
        return json.load(urllib.request.urlopen(u, timeout=8))["results"]
    except Exception:
        return []


# ---------------- dispatch ----------------
cmd = sys.argv[1] if len(sys.argv) > 1 else ""
rest = " ".join(sys.argv[2:]).strip()

if cmd in ("", "now"):
    if cmd == "" and TTY:
        card()
        lib = library()
        sel = fzf(lib, "play ▸ ")
        if sel:
            play_library_line(sel); print(); card()
    else:
        card()

elif cmd in ("pause", "play", "toggle", "p") and not rest:
    osa('tell application "Music" to playpause'); card()
elif cmd in ("next", "n", "skip"):
    osa('tell application "Music" to next track'); import time; time.sleep(.3); card()
elif cmd in ("prev", "back", "b"):
    osa('tell application "Music" to previous track'); import time; time.sleep(.3); card()
elif cmd == "stop":
    osa('tell application "Music" to stop'); print("■ stopped")
elif cmd in ("love", "like"):
    osa('tell application "Music" to set loved of current track to true'); print("♥ loved")

elif cmd == "play":            # fuzzy-play from library (agent-friendly)
    lib = library()
    ql = rest.lower()
    hits = [l for l in lib if ql in l.lower()]
    if not hits:
        print(f"no library track matching '{rest}'"); sys.exit(1)
    line = fzf(hits, "play ▸ ") if (TTY and len(hits) > 1) else hits[0]
    if line:
        play_library_line(line); card()

elif cmd == "search":          # catalog search -> pick -> play (library if owned, else open in Music)
    if not rest:
        print("usage: tess music search <query>"); sys.exit(1)
    res = catalog(rest)
    if not res:
        print(f"nothing found for '{rest}'"); sys.exit(1)
    lines = [f"{r['trackName']} — {r['artistName']}  ·  {r.get('collectionName','')}" for r in res]
    if TTY and len(res) > 1:
        sel = fzf(lines, "search ▸ ")
        if not sel:
            sys.exit(0)
        pick = res[lines.index(sel)]
    else:
        pick = res[0]
    name, artist = pick["trackName"], pick["artistName"]
    # if it's in your library, play it directly (auto-plays); otherwise open in the native Music app
    lib = library()
    owned = next((l for l in lib if name.lower() in l.lower() and artist.split("&")[0].strip().lower() in l.lower()), None)
    if owned:
        play_library_line(owned)
        print(f"  ▶ {name} — {artist}  {C.grey}(from your library){C.r}")
    else:
        # Music's own URL handler → native app, bypasses cmux's browser. Catalog tracks open the page (press play).
        u = pick["trackViewUrl"].replace('"', '')
        subprocess.run(["osascript", "-e", f'tell application "Music" to open location "{u}"'])
        subprocess.run(["osascript", "-e", 'tell application "Music" to activate'])
        print(f"  ▶ opened in Music: {C.bold}{name}{C.r} — {artist}  {C.grey}(press play — catalog songs can't auto-start via script){C.r}")
    render_art(pick["artworkUrl100"].replace("100x100bb", "450x450bb"))

else:
    # bare `tess music <words>` -> treat as a library fuzzy-play
    subprocess.run([sys.argv[0]] if False else ["python3", os.path.abspath(__file__), "play", cmd + (" " + rest if rest else "")])
