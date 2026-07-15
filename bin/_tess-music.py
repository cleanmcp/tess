#!/usr/bin/env python3
"""tess music — Apple Music from the terminal: album art, fuzzy-play, catalog search,
plus a library engine: sort/filter/group anything, build playlists, stats, rate/love.
Interactive for humans, param-driven for agents.

  tess music                 now playing + art, then fuzzy-pick a library song
  tess music now             now playing + album art
  tess music play <query>    fuzzy-play a library track (id:<n> works too)
  tess music search <query>  search the Apple Music catalog -> pick -> play
  tess music pause|next|prev|stop

library engine — every read takes: [text] --filter "f<op>v" --sort <field> --limit N --json --fresh
  tess music lib             query the whole collection — library + playlist-only tracks
                             (filter inlib=false for playlist-only) · --cols a,b,c · --play ·
                             --to-playlist <name> · --ids 12,34 hand-picked set, order kept
  tess music top [N]         most played         tess music recent [N]   latest adds
  tess music loved           favorites           tess music playlists    playlists + counts
  tess music artists|albums|genres|years [--by tracks|plays|time]
  tess music stats           library overview
  tess music love|unlove [query|id:N]        no arg = current track
  tess music rate [query|id:N] <0-5>         e.g. tess music rate id:1505 4.5

fields   name artist album albumartist genre year duration plays played added rating loved size id inlib
filters  = contains · == exact · != · > >= < <=     (quote them: --filter "plays>=10")
         dates take 2024-06-01 | 30d | 12w | 6m | 1y   ·   rating in stars 0-5
  e.g.   tess music lib --filter "added=90d" --sort plays          what's hot this quarter
         tess music lib rap --filter "year>=2020" --to-playlist "new rap"
         tess music lib --filter loved=true --play                 queue every favorite
"""
import os, sys, json, re, time, subprocess, tempfile, shutil, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tess_common import C  # noqa: E402

TTY = sys.stdout.isatty()
LIB_CACHE = os.path.join(os.path.expanduser("~"), ".local/share/tess/music-library.json")
LIB_TTL = 300  # seconds; play counts etc. may lag this much — --fresh forces a re-read


def die(msg):
    print(msg); sys.exit(1)


def osa(script, timeout=20):
    try:
        return subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout).stdout.strip()
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
        tmp = tempfile.mktemp(suffix=".jpg")
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


# ---------------- library engine ----------------
# One batched Apple Event per property (JXA) -> whole collection with metadata in seconds,
# instead of an AppleScript repeat-loop of per-track events. Sweeps the library AND every
# user playlist: tracks added straight to a playlist never appear in library playlist 1,
# so a library-only read silently misses them. Deduped by database ID; inlib marks source.
JXA = '''(() => {
  const M = Application("Music");
  const dts = a => a ? a.map(d => d ? Math.floor(d.getTime() / 1000) : null) : null;
  const cols = t => {
    const grab = f => { try { return t[f]() } catch (e) { return null } };
    return {
      id: grab("databaseID"), pid: grab("persistentID"), name: grab("name"), artist: grab("artist"),
      album: grab("album"), albumArtist: grab("albumArtist"), genre: grab("genre"),
      year: grab("year"), duration: grab("duration"), plays: grab("playedCount"),
      lastPlayed: dts(grab("playedDate")), added: dts(grab("dateAdded")),
      rating: grab("rating"), loved: grab("favorited") || grab("loved"), size: grab("size")
    };
  };
  const seen = new Set(), out = [];
  const emit = (c, inlib) => {
    const n = (c.name || []).length;
    for (let i = 0; i < n; i++) {
      const id = c.id ? c.id[i] : null;
      if (id === null || id === undefined || seen.has(id)) continue;
      seen.add(id);
      const r = {inlib: inlib};
      for (const k in c) r[k] = c[k] ? c[k][i] : null;
      out.push(r);
    }
  };
  emit(cols(M.libraryPlaylists[0].tracks), true);
  for (const p of M.userPlaylists()) {
    try { emit(cols(p.tracks), false) } catch (e) {}
  }
  return JSON.stringify(out);
})()'''


def fetch_library(fresh=False):
    """Every track (library + playlist-only) as a row dict. Cached briefly."""
    if not fresh:
        try:
            c = json.load(open(LIB_CACHE))
            if time.time() - c["at"] < LIB_TTL:
                return c["rows"]
        except Exception:
            pass
    try:
        p = subprocess.run(["osascript", "-l", "JavaScript", "-e", JXA],
                           capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        die("Music library read timed out — is Music.app responding?")
    if p.returncode != 0 or not p.stdout.strip():
        die(f"couldn't read the Music library: {p.stderr.strip()[:200]}")
    rows = json.loads(p.stdout)
    try:
        os.makedirs(os.path.dirname(LIB_CACHE), exist_ok=True)
        json.dump({"at": time.time(), "rows": rows}, open(LIB_CACHE, "w"))
    except Exception:
        pass
    return rows


def drop_cache():
    try:
        os.remove(LIB_CACHE)
    except OSError:
        pass


FIELDS = {}  # alias -> (row key, kind)   kind: s text · n number · d date · b bool
for _aliases, _key, _kind in (
    ("name title song", "name", "s"), ("artist", "artist", "s"), ("album", "album", "s"),
    ("albumartist album_artist", "albumArtist", "s"), ("genre", "genre", "s"),
    ("year", "year", "n"), ("duration time length", "duration", "n"),
    ("plays playcount play_count", "plays", "n"),
    ("played lastplayed last_played last", "lastPlayed", "d"),
    ("added dateadded date_added", "added", "d"),
    ("rating stars", "rating", "n"), ("loved favorited fav", "loved", "b"),
    ("size", "size", "n"), ("id", "id", "n"), ("inlib library", "inlib", "b"),
    ("pid persistentid persistent_id", "pid", "s"),
):
    for _a in _aliases.split():
        FIELDS[_a] = (_key, _kind)
FIELD_HELP = "name artist album albumartist genre year duration plays played added rating loved size id inlib"


def field(alias):
    f = FIELDS.get((alias or "").strip().lower())
    if not f:
        die(f"unknown field '{alias}' — fields: {FIELD_HELP}")
    return f


def parse_when(v):
    """'30d'/'12w'/'6m'/'1y' -> epoch cutoff that long ago; '2024[-06[-15]]' -> epoch."""
    m = re.match(r"^(\d+(?:\.\d+)?)([dwmy])$", v)
    if m:
        mult = {"d": 86400, "w": 604800, "m": 2629800, "y": 31557600}[m.group(2)]
        return time.time() - float(m.group(1)) * mult
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$", v)
    if m:
        import datetime
        try:
            return datetime.datetime(int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)).timestamp()
        except ValueError:
            return None
    return None


def compile_filter(expr):
    m = re.match(r"^([A-Za-z_]+)\s*(==|!=|>=|<=|=|>|<)\s*(.*)$", (expr or "").strip())
    if not m:
        die(f"bad filter '{expr}' — use field<op>value, e.g. \"plays>=10\", artist=drake, added=90d")
    alias, op, raw = m.groups()
    key, kind = field(alias)
    raw = raw.strip().strip('"').strip("'")
    if kind == "s":
        v = raw.lower()
        if op in ("=",):
            return lambda r: v in (r.get(key) or "").lower()
        if op == "==":
            return lambda r: v == (r.get(key) or "").lower()
        if op == "!=":
            return lambda r: v not in (r.get(key) or "").lower()
        die(f"'{op}' doesn't work on text fields — use = (contains), == (exact), !=")
    if kind == "b":
        if op not in ("=", "==", "!="):
            die(f"'{op}' doesn't work on {alias} — use loved=true / loved=false")
        want = raw.lower() in ("1", "true", "yes", "y", "on")
        neg = op == "!="
        return lambda r: (bool(r.get(key)) == want) != neg
    if kind == "d":
        val = parse_when(raw)
        if val is None:
            die(f"bad date '{raw}' — use 2024-06-15 or 30d / 12w / 6m / 1y")
        if op == "=":  # "added=90d" reads as "in the last 90 days"
            op = ">="
    else:
        mm = re.match(r"^(\d+):(\d{1,2})$", raw)
        if key == "duration" and mm:
            val = int(mm.group(1)) * 60 + int(mm.group(2))
        else:
            try:
                val = float(raw)
            except ValueError:
                die(f"'{raw}' isn't a number (filter on {alias})")
            if key == "rating" and val <= 5:
                val *= 20  # stars -> Music's 0-100 scale
    ops = {"=": lambda a, b: a == b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
           ">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b}
    f = ops[op]
    return lambda r: r.get(key) is not None and f(r.get(key), val)


def select(rows, text, filters):
    if text:
        t = text.lower()
        rows = [r for r in rows
                if t in f"{r.get('name') or ''}\t{r.get('artist') or ''}\t{r.get('album') or ''}".lower()]
    for f in filters:
        rows = [r for r in rows if f(r)]
    return rows


def sort_rows(rows, alias, asc=None):
    key, kind = field(alias)
    if asc is None:
        asc = kind == "s"  # text sorts A-Z; numbers/dates default to biggest/newest first
    def missing(r):
        v = r.get(key)
        if v is None or v == "":
            return True
        return v == 0 if (kind == "d" or key in ("year", "rating")) else False  # 0 = unknown/unrated
    have = [r for r in rows if not missing(r)]
    rest = [r for r in rows if missing(r)]
    if kind == "s":
        sk = lambda r: ((r.get(key) or "").lower(), (r.get("album") or "").lower(),
                        r.get("year") or 0, (r.get("name") or "").lower())
    else:
        sk = lambda r: (r.get(key) or 0, (r.get("name") or "").lower())
    have.sort(key=sk, reverse=not asc)
    return have + rest


# ---------------- output ----------------
def fmt_dur(s):
    return f"{int(s) // 60}:{int(s) % 60:02d}" if s else ""


def fmt_when(e):
    return time.strftime("%Y-%m-%d", time.localtime(e)) if e else ""


def iso(e):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(e)) if e else None


def cell(r, alias):
    key, kind = field(alias)
    v = r.get(key)
    if key == "duration":
        return fmt_dur(v)
    if kind == "d":
        return fmt_when(v)
    if key == "rating":
        return f"★{v / 20:g}" if v else ""
    if key == "loved":
        return "♥" if v else ""
    if key == "size":
        return f"{v / 1048576:.1f}M" if v else ""
    if v is None or (key == "year" and not v):
        return ""
    return str(v)


def raw_cell(r, alias):
    key, kind = field(alias)
    v = r.get(key)
    if v is None:
        return ""
    if key == "duration":
        return str(int(v))
    if kind == "d":
        return iso(v) or ""
    if key == "rating":
        return f"{v / 20:g}"
    if key == "loved":
        return "true" if v else "false"
    return str(v)


NUMERIC_COLS = {"plays", "playcount", "play_count", "year", "duration", "time", "length",
                "size", "rating", "stars", "id", "tracks", "hours"}
CAPS = {"name": 40, "title": 40, "song": 40, "artist": 26, "album": 28,
        "albumartist": 24, "album_artist": 24, "genre": 18}


def print_table(heads, data, numeric=()):
    if not data:
        print(f"  {C.grey}nothing matched{C.r}"); return
    w = [max(len(heads[i]), max(len(d[i]) for d in data)) for i in range(len(heads))]
    w = [min(w[i], CAPS.get(heads[i], 99)) for i in range(len(heads))]
    def pad(s, i):
        s = s if len(s) <= w[i] else s[:w[i] - 1] + "…"
        return s.rjust(w[i]) if heads[i] in numeric else s.ljust(w[i])
    print("  " + C.grey + "  ".join(pad(h, i) for i, h in enumerate(heads)).rstrip() + C.r)
    for d in data:
        print("  " + "  ".join(pad(c, i) for i, c in enumerate(d)).rstrip())


def jrow(r):
    return {"id": r.get("id"), "name": r.get("name"), "artist": r.get("artist"),
            "album": r.get("album"), "album_artist": r.get("albumArtist"),
            "genre": r.get("genre"), "year": r.get("year"),
            "duration": int(r.get("duration") or 0), "plays": r.get("plays") or 0,
            "rating": (r.get("rating") or 0) / 20, "loved": bool(r.get("loved")),
            "added": iso(r.get("added")), "last_played": iso(r.get("lastPlayed")),
            "size": r.get("size"), "inlib": bool(r.get("inlib", True)),
            "pid": r.get("pid")}


# ---------------- actions ----------------
# database IDs churn when iCloud sync re-registers tracks; persistent IDs survive.
# All actions key on persistent ID, falling back to a playlist sweep for tracks
# that were never added to the library.
def track_ref(row):
    pid = row.get("pid") if isinstance(row, dict) else None
    if pid:
        return f'(first track of library playlist 1 whose persistent ID is "{pid}")'
    return f'(first track of library playlist 1 whose database ID is {int(row["id"] if isinstance(row, dict) else row)})'


def play_id(row):
    osa(f'tell application "Music" to play {track_ref(row)}')


def esc_as(s):
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def playlist_fill(name, pids):
    """Create/replace a real user playlist with these tracks (persistent IDs), in order."""
    e = esc_as(name)
    idl = ", ".join(f'"{p}"' for p in pids)
    script = f'''tell application "Music"
  if not (exists user playlist "{e}") then make new user playlist with properties {{name:"{e}"}}
  try
    delete every track of user playlist "{e}"
  end try
  repeat with i in {{{idl}}}
    set src to missing value
    try
      set src to (first track of library playlist 1 whose persistent ID is (contents of i))
    end try
    if src is missing value then
      repeat with p in user playlists
        if src is missing value then
          try
            set src to (first track of p whose persistent ID is (contents of i))
          end try
        end if
      end repeat
    end if
    if src is not missing value then
      try
        duplicate src to user playlist "{e}"
      end try
    end if
  end repeat
  return count of tracks of user playlist "{e}"
end tell'''
    try:
        p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        die(f"filling playlist '{name}' timed out")
    if p.returncode != 0:
        die(f"couldn't build playlist '{name}': {p.stderr.strip()[:200]}")
    return int(p.stdout.strip() or 0)


def set_prop(target, prop, value):
    """Set a track property; 'favorited' falls back to 'loved' on older Music versions."""
    for nm in (("favorited", "loved") if prop == "favorited" else (prop,)):
        p = subprocess.run(["osascript", "-e", f'tell application "Music" to set {nm} of {target} to {value}'],
                           capture_output=True, text=True, timeout=20)
        if p.returncode == 0:
            drop_cache()
            return True
    return False


def fzf(lines, prompt):
    if not (TTY and shutil.which("fzf")):
        return None
    p = subprocess.run(["fzf", "--prompt", prompt, "--height", "60%", "--reverse"],
                       input="\n".join(lines), capture_output=True, text=True)
    return p.stdout.strip() or None


def resolve_track(q, strict=False):
    """query or id:<n> -> one library row. strict (writes): ambiguity is an error when
    non-interactive; loose (play): best guess = most-played match."""
    q = (q or "").strip()
    rows = fetch_library()
    m = re.match(r"^id:([0-9A-Fa-f]{8,}|\d+)$", q)
    if m:
        key = m.group(1)
        r = next((r for r in rows if str(r.get("id")) == key
                  or (r.get("pid") or "").upper() == key.upper()), None)
        if not r:
            die(f"no track with id {key}")
        return r
    if not q:
        die("give me a song (or id:<n>)")
    hits = select(rows, q, [])
    if not hits:
        die(f"no library track matching '{q}'")
    hits.sort(key=lambda r: (-(r.get("plays") or 0), (r.get("name") or "").lower()))
    if len(hits) == 1:
        return hits[0]
    if TTY and shutil.which("fzf"):
        lines = [f"{r.get('name') or ''}\t{r.get('artist') or ''}" for r in hits]
        sel = fzf(lines, "which ▸ ")
        if not sel:
            sys.exit(0)
        return hits[lines.index(sel)]
    if strict:
        print(f"{len(hits)} matches for '{q}' — be specific or use id:<n>:")
        for r in hits[:8]:
            print(f"  id:{r['id']}\t{r.get('name')} — {r.get('artist')}")
        sys.exit(1)
    return hits[0]


def do_play(text):
    r = resolve_track(text)
    play_id(r); card()


# ---------------- flag parsing ----------------
class _O:
    pass


def parse_flags(argv):
    o = _O()
    o.text, o.filters, o.sort, o.asc, o.limit = [], [], None, None, None
    o.cols, o.json, o.fresh, o.play, o.to_playlist, o.by, o.ids = None, False, False, False, None, None, None
    def need(i, flag):
        if i >= len(argv):
            die(f"{flag} needs a value")
        return argv[i]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--json", "-j"):
            o.json = True
        elif a == "--fresh":
            o.fresh = True
        elif a == "--asc":
            o.asc = True
        elif a == "--desc":
            o.asc = False
        elif a == "--play":
            o.play = True
        elif a in ("--sort", "-s"):
            i += 1; o.sort = need(i, a); field(o.sort)
        elif a in ("--filter", "-f", "--where"):
            i += 1; o.filters.append(compile_filter(need(i, a)))
        elif a in ("--limit", "-n", "--top"):
            i += 1
            try:
                o.limit = int(need(i, a))
            except ValueError:
                die(f"{a} needs a number")
        elif a == "--cols":
            i += 1
            o.cols = [c.strip().lower() for c in need(i, a).split(",") if c.strip()]
            for c in o.cols:
                field(c)
        elif a == "--ids":
            i += 1
            o.ids = [x.strip() for x in re.split(r"[,\s]+", need(i, a).strip()) if x.strip()]
            if not all(re.fullmatch(r"\d+|[0-9A-Fa-f]{8,}", x) for x in o.ids):
                die("--ids takes database ids or persistent ids, e.g. --ids 1505,9F60B4A20D3E88C2")
        elif a == "--to-playlist":
            i += 1; o.to_playlist = need(i, a)
        elif a == "--by":
            i += 1; o.by = need(i, a).lower()
        elif a.startswith("--"):
            die(f"unknown flag {a} — see: tess help music")
        else:
            m = re.match(r"^([A-Za-z_]+)(==|!=|>=|<=|=|>|<)(.+)$", a)
            if m and m.group(1).lower() in FIELDS:
                o.filters.append(compile_filter(a))  # bare artist=drake works too
            else:
                o.text.append(a)
        i += 1
    o.text = " ".join(o.text).strip()
    return o


def with_defaults(argv, sort, limit=25):
    argv = list(argv)
    if argv and argv[0].isdigit():
        argv = ["--limit", argv[0]] + argv[1:]
    pre = ["--sort", sort]
    if not any(a in ("--limit", "-n", "--top") for a in argv):
        pre += ["--limit", str(limit)]
    return pre + argv


# ---------------- library views ----------------
def default_cols(sort_alias):
    cols = ["name", "artist", "album", "plays", "added"]
    if sort_alias:
        k = field(sort_alias)[0]
        if k not in [field(c)[0] for c in cols]:
            cols.append(sort_alias.lower())
    return cols


def cmd_lib(argv):
    o = parse_flags(argv)
    rows = fetch_library(o.fresh)
    if o.ids is not None:  # explicit hand-picked set, kept in the order given
        by_id = {str(r.get("id")): r for r in rows}
        by_id.update({str(r.get("pid") or "").upper(): r for r in rows if r.get("pid")})
        miss = [x for x in o.ids if x.upper() not in by_id and x not in by_id]
        if miss:
            die(f"no track with id: {', '.join(miss)}")
        rows = select([by_id.get(x) or by_id[x.upper()] for x in o.ids], o.text, o.filters)
        if o.sort:
            rows = sort_rows(rows, o.sort, o.asc)
    else:
        rows = select(rows, o.text, o.filters)
        rows = sort_rows(rows, o.sort or "artist", o.asc)
    total = len(rows)
    if o.limit is not None:
        rows = rows[:o.limit]
    if o.to_playlist or o.play:
        if not rows:
            die("nothing matched — not touching playback")
        ids = [r.get("pid") or str(r["id"]) for r in rows]
        if o.to_playlist:
            if len(ids) > 300:
                print(f"  {C.grey}copying {len(ids)} tracks into '{o.to_playlist}' — sit tight{C.r}")
            got = playlist_fill(o.to_playlist, ids)
            drop_cache()
            print(f"  ♫ playlist {C.bold}{o.to_playlist}{C.r} — {got} tracks")
            if o.play:
                osa(f'tell application "Music" to play user playlist "{esc_as(o.to_playlist)}"'); card()
            return
        if len(ids) == 1:
            play_id(rows[0]); card()
        else:
            playlist_fill("tess queue", ids)
            osa('tell application "Music" to play user playlist "tess queue"')
            print(f"  ♫ queued {len(ids)} tracks {C.grey}(playlist 'tess queue'){C.r}")
            card()
        return
    if o.json:
        print(json.dumps([jrow(r) for r in rows], ensure_ascii=False, indent=1))
        return
    cols = o.cols or default_cols(o.sort)
    if TTY:
        print_table(cols, [[cell(r, c) for c in cols] for r in rows], NUMERIC_COLS)
        print(f"  {C.grey}{len(rows)}/{total} tracks{C.r}")
    else:
        cols = cols if "id" in cols else ["id"] + cols
        print("\t".join(cols))
        for r in rows:
            print("\t".join(raw_cell(r, c) for c in cols))


def cmd_group(kind, argv):
    o = parse_flags(argv)
    rows = select(fetch_library(o.fresh), o.text, o.filters)
    g = {}
    for r in rows:
        if kind == "albums":
            k = (r.get("albumArtist") or r.get("artist") or "—", r.get("album") or "—")
            disp = f"{k[1]} — {k[0]}"
        elif kind == "years":
            k = r.get("year") or 0
            disp = str(k) if k else "—"
        else:
            k = r.get("artist" if kind == "artists" else "genre") or "—"
            disp = k
        e = g.setdefault(k, {"k": k, "name": disp, "tracks": 0, "plays": 0, "secs": 0.0})
        e["tracks"] += 1
        e["plays"] += r.get("plays") or 0
        e["secs"] += r.get("duration") or 0
    items = list(g.values())
    by = o.by or {"artists": "plays", "albums": "plays", "genres": "tracks", "years": "year"}[kind]
    if by in ("year", "name"):
        items.sort(key=lambda e: (e["k"] == 0 or e["name"] == "—", e["k"] if by == "year" else e["name"].lower()),
                   reverse=o.asc is False)
    elif by in ("tracks", "plays"):
        items.sort(key=lambda e: (-e[by], e["name"].lower()) if o.asc is not True else (e[by], e["name"].lower()))
    elif by == "time":
        items.sort(key=lambda e: (-e["secs"], e["name"].lower()) if o.asc is not True else (e["secs"], e["name"].lower()))
    else:
        die(f"--by takes tracks | plays | time | name{' | year' if kind == 'years' else ''}")
    total = len(items)
    if o.limit is not None:
        items = items[:o.limit]
    head = kind[:-1]
    if o.json:
        print(json.dumps([{head: e["name"], "tracks": e["tracks"], "plays": e["plays"],
                           "hours": round(e["secs"] / 3600, 2)} for e in items], ensure_ascii=False, indent=1))
        return
    data = [[e["name"], str(e["tracks"]), str(e["plays"]), f"{e['secs'] / 3600:.1f}"] for e in items]
    if TTY:
        print_table([head, "tracks", "plays", "hours"], data, NUMERIC_COLS)
        print(f"  {C.grey}{len(items)}/{total} {kind}{C.r}")
    else:
        print("\t".join([head, "tracks", "plays", "hours"]))
        for d in data:
            print("\t".join(d))


def cmd_stats(argv):
    o = parse_flags(argv)
    rows = select(fetch_library(o.fresh), o.text, o.filters)
    if not rows:
        die("nothing matched")
    secs = sum(r.get("duration") or 0 for r in rows)
    size = sum(r.get("size") or 0 for r in rows)
    plays = sum(r.get("plays") or 0 for r in rows)
    arts, gens = {}, {}
    for r in rows:
        a = r.get("artist") or "—"
        arts[a] = arts.get(a, 0) + (r.get("plays") or 0)
        gn = r.get("genre") or "—"
        gens[gn] = gens.get(gn, 0) + 1
    albums = {(r.get("albumArtist") or r.get("artist") or "", r.get("album") or "") for r in rows}
    loved = sum(1 for r in rows if r.get("loved"))
    rated = sum(1 for r in rows if r.get("rating"))
    top = max(rows, key=lambda r: r.get("plays") or 0)
    newest = max(rows, key=lambda r: r.get("added") or 0)
    top_art = max(arts, key=arts.get) if arts else "—"
    top_gen = max(gens, key=gens.get) if gens else "—"
    if o.json:
        print(json.dumps({"tracks": len(rows), "hours": round(secs / 3600, 1), "gb": round(size / 1e9, 2),
                          "artists": len(arts), "albums": len(albums), "genres": len(gens),
                          "plays": plays, "loved": loved, "rated": rated,
                          "top_artist": top_art, "top_genre": top_gen,
                          "most_played": jrow(top), "last_added": jrow(newest)}, ensure_ascii=False, indent=1))
        return
    print(f"  ♫ {C.bold}{len(rows)} tracks{C.r} {C.grey}· {secs / 3600:.1f} h · {size / 1e9:.2f} GB{C.r}")
    print(f"    {C.grey}artists{C.r} {len(arts)}  {C.grey}albums{C.r} {len(albums)}  "
          f"{C.grey}genres{C.r} {len(gens)}  {C.grey}plays{C.r} {plays}  "
          f"{C.grey}loved{C.r} {loved}  {C.grey}rated{C.r} {rated}")
    print(f"    {C.grey}top artist {C.r}{top_art} {C.grey}({arts.get(top_art, 0)} plays){C.r}")
    print(f"    {C.grey}top genre  {C.r}{top_gen} {C.grey}({gens.get(top_gen, 0)} tracks){C.r}")
    print(f"    {C.grey}most played{C.r} {top.get('name')} — {top.get('artist')} {C.grey}({top.get('plays') or 0}×){C.r}")
    print(f"    {C.grey}last added {C.r}{newest.get('name')} — {newest.get('artist')} {C.grey}({fmt_when(newest.get('added'))}){C.r}")


def cmd_playlists():
    out = osa('''tell application "Music"
  set o to ""
  repeat with p in user playlists
    set o to o & (name of p) & tab & (count of tracks of p) & linefeed
  end repeat
  return o
end tell''', timeout=60)
    lines = [l.split("\t") for l in out.splitlines() if "\t" in l]
    if not lines:
        print(f"  {C.grey}no playlists{C.r}"); return
    if TTY:
        print_table(["playlist", "tracks"], lines, {"tracks"})
    else:
        print("playlist\ttracks")
        for l in lines:
            print("\t".join(l))


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
        rows = fetch_library()
        lines = [f"{r.get('name') or ''}\t{r.get('artist') or ''}" for r in rows]
        sel = fzf(lines, "play ▸ ")
        if sel:
            play_id(rows[lines.index(sel)]); print(); card()
    else:
        card()

elif cmd in ("-h", "--help", "help"):
    print(__doc__.strip())

elif cmd in ("pause", "play", "toggle", "p") and not rest:
    osa('tell application "Music" to playpause'); card()
elif cmd in ("next", "n", "skip"):
    osa('tell application "Music" to next track'); time.sleep(.3); card()
elif cmd in ("prev", "back", "b"):
    osa('tell application "Music" to previous track'); time.sleep(.3); card()
elif cmd == "stop":
    osa('tell application "Music" to stop'); print("■ stopped")

elif cmd in ("love", "like", "unlove", "unlike"):
    val = "false" if cmd.startswith("un") else "true"
    if rest:
        r = resolve_track(rest, strict=True)
        ok = set_prop(track_ref(r), "favorited", val)
        label = f"{r.get('name')} — {r.get('artist')}"
    else:
        ok = set_prop("current track", "favorited", val)
        n = now()
        label = f"{n['name']} — {n['artist']}" if n else "current track"
    print((("♥ " if val == "true" else "♡ ") + label) if ok else "couldn't set — is anything playing / does the track exist?")

elif cmd == "rate":
    args = sys.argv[2:]
    if not args:
        die("usage: tess music rate [query|id:N] <0-5>")
    try:
        stars = float(args[-1])
    except ValueError:
        die("last arg must be stars 0-5 (e.g. tess music rate id:1505 4.5)")
    if not 0 <= stars <= 5:
        die("stars go 0-5")
    tgt = " ".join(args[:-1]).strip()
    if tgt:
        r = resolve_track(tgt, strict=True)
        ok = set_prop(track_ref(r), "rating", int(round(stars * 20)))
        label = f"{r.get('name')} — {r.get('artist')}"
    else:
        ok = set_prop("current track", "rating", int(round(stars * 20)))
        n = now()
        label = f"{n['name']} — {n['artist']}" if n else "current track"
    print(f"★{stars:g}  {label}" if ok else "couldn't set — is anything playing / does the track exist?")

elif cmd in ("lib", "library", "ls", "tracks", "all"):
    cmd_lib(sys.argv[2:])
elif cmd == "top":
    cmd_lib(with_defaults(sys.argv[2:], "plays"))
elif cmd in ("recent", "new", "latest"):
    cmd_lib(with_defaults(sys.argv[2:], "added"))
elif cmd == "loved":
    cmd_lib(["--filter", "loved=true", "--sort", "plays"] + sys.argv[2:])
elif cmd in ("artists", "albums", "genres", "years"):
    cmd_group(cmd, sys.argv[2:])
elif cmd == "stats":
    cmd_stats(sys.argv[2:])
elif cmd == "playlists":
    cmd_playlists()

elif cmd == "play":            # fuzzy-play from library (agent-friendly; id:<n> exact)
    do_play(rest)

elif cmd == "search":          # catalog search -> pick -> play (library if owned, else open in Music)
    if not rest:
        die("usage: tess music search <query>")
    res = catalog(rest)
    if not res:
        die(f"nothing found for '{rest}'")
    lines = [f"{r['trackName']} — {r['artistName']}  ·  {r.get('collectionName', '')}" for r in res]
    if TTY and len(res) > 1:
        sel = fzf(lines, "search ▸ ")
        if not sel:
            sys.exit(0)
        pick = res[lines.index(sel)]
    else:
        pick = res[0]
    name, artist = pick["trackName"], pick["artistName"]
    # if it's in your library, play it directly (auto-plays); otherwise open in the native Music app
    rows = fetch_library()
    owned = next((r for r in rows if name.lower() in (r.get("name") or "").lower()
                  and artist.split("&")[0].strip().lower() in (r.get("artist") or "").lower()), None)
    if owned:
        play_id(owned)
        print(f"  ▶ {name} — {artist}  {C.grey}(from your library){C.r}")
    else:
        # Music's own URL handler → native app, bypasses cmux's browser. Catalog tracks open the page (press play).
        u = pick["trackViewUrl"].replace('"', '')
        subprocess.run(["osascript", "-e", f'tell application "Music" to open location "{u}"'])
        subprocess.run(["osascript", "-e", 'tell application "Music" to activate'])
        print(f"  ▶ opened in Music: {C.bold}{name}{C.r} — {artist}  {C.grey}(press play — catalog songs can't auto-start via script){C.r}")
    render_art(pick["artworkUrl100"].replace("100x100bb", "450x450bb"))

else:
    # bare `tess music <words>` -> library fuzzy-play
    do_play((cmd + " " + rest).strip())
