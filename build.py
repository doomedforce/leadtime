"""Build Trailer Math's data: film campaigns from TMDB, trailer views from YouTube.

    python build.py                  # refresh current films, snapshot views, write public/data.json
    python build.py --backfill 3     # also load the last 3 years of releases (for the benchmark)

Needs TMDB_TOKEN (TMDB "API Read Access Token") and YOUTUBE_API_KEY, from the environment or a .env file.
State lives in data/ and is committed, so view history survives between runs.
"""
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
FILMS = ROOT / "data" / "films.json"  # {tmdb id: film with its videos}
VIEWS = ROOT / "data" / "views.json"  # {youtube key: {"snaps": [[iso, views]], "h24", "likes", "comments": int | None}}
OUT = ROOT / "public" / "data.json"
POSTS = ROOT / "posts"                # blog posts, one Markdown file each
SHARE = ROOT / "public" / "f"         # per-film share pages (social previews), generated
SITE = "https://trailermath.com"

WINDOW_BACK, WINDOW_AHEAD = 60, 365  # days around today for "current" films
CURRENT_PAGES = 10                   # 20 films a page, most popular first
BACKFILL_PAGES = 8                   # per half year
ACTIVE_DAYS = 30                     # snapshot views for videos this young; also the snapshot retention
CAMPAIGN_TYPES = {"Teaser", "Trailer"}
# Official channels of US distributors, ranked by how many TMDB-listed official trailers they published.
# Watching them directly catches a trailer within the hour, before TMDB lists it.
STUDIO_CHANNELS = [
    "UCJ6nMHaJPZvsJ-HmUmj1SeA",  # Lionsgate Movies
    "UCjmJDM5pRKbUlVIzDYYWb6g",  # Warner Bros.
    "UCF9imwPMSGz4Vq1NiTWCC7g",  # Paramount Pictures
    "UCz97F7dMxBNOfGYu3rx8aCw",  # Sony Pictures Entertainment
    "UCpy5dRhZd-JbZP4NsrnLt1w",  # NEON
    "UCq0OueAsdxH6b8nyAspwViw",  # Universal Pictures
    "UCuPivVjnfNo4mb3Oog_frZg",  # A24
    "UCf5CjDJvsFvtVIhkfmKAwAA",  # Amazon MGM Studios
    "UC2-BeLxzUBSs0uSrmzWhJuQ",  # 20th Century Studios
    "UCQIjTyWmLEdsfqMQay0yGMA",  # Angel
    "UCU4SM3j_9TNWaSu8KdGV50g",  # Focus Features
    "UCb6-VM5UQ4Czj_d3m9EPGfg",  # MUBI
    "UCOn923UnbV8H9zo_lO6ZCRw",  # Independent Film Company
    "UCruD_lL-5fmllpKMSL-yCyQ",  # Sony Pictures Classics
    "UCb9ME2w6Y_4jChUVlWdltVg",  # GKIDS Films
    "UC_5niPa-d35gg88HaS7RrIw",  # Disney
    "UCor9rW6PgxSQ9vUPWQdnaYQ",  # Searchlight Pictures
    "UCvE8nyjdQG0_rgx9u3oqadw",  # Well Go USA Entertainment
    "UCafnP6JPjVq8AahYaThUelg",  # Bleecker Street
    "UCH45phx_o8pNt9PwbjxWhcA",  # Roadside Attractions
    "UCpR3kmSyTYszJHWEcmpcnFQ",  # Vertical
    "UCvC4D8onUfXzvjTOM-dBfEA",  # Marvel Entertainment
    "UCfnXpb2MPBULONuZCyaKgmA",  # Briarcliff Entertainment
    "UCiifkYAs_bq1pt_zbNAzYGg",  # DC
    "UC_IRYSp4auq7hKLvziWVH6w",  # Pixar
    "UCneoi6WTgRjMh4otvpwzv8w",  # Magnolia Pictures & Magnet Releasing
    "UCnLF1F3-SWsuSJEh1qIJS9w",  # Black Bear
]
CHANNEL_LOOKBACK_HOURS = 48  # uploads older than this are TMDB's job
MAX_LEAD = 1100                      # a "first trailer" 3+ years out is a data error, not a campaign


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"Accept": "application/json", **(headers or {})})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503) or attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def tmdb(path, **params):
    q = urllib.parse.urlencode(params)
    return get_json(f"https://api.themoviedb.org/3{path}?{q}",
                    {"Authorization": f"Bearer {os.environ['TMDB_TOKEN']}"})


# ---------- pure logic (tested in test_build.py) ----------

def us_release(release_dates):
    """Earliest US wide theatrical date (TMDB type 3), as YYYY-MM-DD, or None."""
    for country in release_dates.get("results", []):
        if country["iso_3166_1"] == "US":
            dates = [d["release_date"][:10] for d in country["release_dates"] if d["type"] == 3]
            return min(dates) if dates else None
    return None


def days_out(release, published):
    """Days between a video's publish date and opening day (negative = after opening)."""
    return (date.fromisoformat(release) - date.fromisoformat(published[:10])).days


def first_lead(film):
    """How far before opening the campaign's first teaser or trailer landed, in days."""
    leads = [days_out(film["release"], v["published"]) for v in film["videos"] if v.get("type") != "Spot"]
    leads = [d for d in leads if 0 <= d <= MAX_LEAD]
    return max(leads) if leads else None


def views_at_24h(published, snaps, max_gap_hours=12):
    """Views 24h after publish, interpolated between the snapshots either side of that moment.

    None when we have no snapshot on both sides, or the two are too far apart to trust.
    """
    target = datetime.fromisoformat(published.replace("Z", "+00:00")) + timedelta(hours=24)
    pts = sorted((datetime.fromisoformat(t), v) for t, v in snaps)
    before = [p for p in pts if p[0] <= target]
    after = [p for p in pts if p[0] >= target]
    if not before or not after:
        return None
    (t0, v0), (t1, v1) = before[-1], after[0]
    if (t1 - t0) > timedelta(hours=max_gap_hours):
        return None
    if t1 == t0:
        return v0
    return round(v0 + (v1 - v0) * (target - t0) / (t1 - t0))


def norm_title(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def match_upload(title, films, today):
    """The tracked film a studio upload is a trailer or teaser for, or None.

    The film's title must appear in the video title; the longest match wins
    ("Wicked: For Good" over "Wicked"). Titles under 4 characters are too ambiguous to match.
    """
    if not re.search(r"trailer|teaser", title, re.I):
        return None
    t, recent, best = norm_title(title), str(today - timedelta(days=30)), None
    for mid, f in films.items():
        n = norm_title(f["title"])
        if f["release"] >= recent and len(n) >= 4 and n in t:
            if best is None or len(n) > len(norm_title(films[best]["title"])):
                best = mid
    return best


def is_reupload(film, published, hours=6):
    """Studios often post the same trailer twice within minutes (a vertical cut, a fixed re-upload)."""
    t = datetime.fromisoformat(published.replace("Z", "+00:00"))
    return any(abs(datetime.fromisoformat(v["published"].replace("Z", "+00:00")) - t) < timedelta(hours=hours)
               for v in film["videos"])


def keep_found(old, new):
    """Carry over channel-found videos TMDB hasn't listed yet, so a refresh doesn't drop them.

    If TMDB lists another upload of a channel-found trailer, the channel one stays: its views were caught from the start.
    """
    have = {v["key"] for v in new["videos"]}
    extra = [v for v in (old or {}).get("videos", []) if v.get("found") == "channel" and v["key"] not in have]
    tmdb = [v for v in new["videos"] if not is_reupload({"videos": extra}, v["published"])]
    return {**new, "videos": sorted(tmdb + extra, key=lambda v: v["published"])}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def md_inline(s):
    s = esc(s)
    s = re.sub(r"\[([^\]]+)\]\(((?:https?://|#/)[^)\s]+)\)", r'<a href="\2">\1</a>', s)  # web and in-site links only
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)


def md_to_html(text):
    """The Markdown posts need: paragraphs, ## headings, - lists, links, **bold**, *italics*."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        if lines[0].startswith("## "):
            out.append(f"<h2>{md_inline(lines[0][3:])}</h2>")
        elif all(l.startswith("- ") for l in lines):
            out.append("<ul>" + "".join(f"<li>{md_inline(l[2:])}</li>" for l in lines) + "</ul>")
        else:
            out.append(f"<p>{md_inline(' '.join(l.strip() for l in lines))}</p>")
    return "\n".join(out)


def parse_post(text, slug):
    """A post file: `---` front matter (title, date, film, summary, author, draft), then Markdown.

    Drafts aren't published.
    """
    m = re.match(r"---\s*\n(.*?)\n---\s*\n(.*)", text, re.S)
    if not m:
        raise ValueError(f"post {slug}: missing front matter")
    meta = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    if meta.get("draft", "").lower() == "true":
        return None
    date.fromisoformat(meta["date"])  # fail the build on a bad date rather than mis-sorting
    body = m.group(2)
    return {"slug": slug, "title": meta["title"], "date": meta["date"], "film": meta.get("film") or None,
            "summary": meta.get("summary", ""), "author": meta.get("author", ""),
            "minutes": max(1, round(len(body.split()) / 230)), "html": md_to_html(body)}


def share_page(title, description, image, target, large=False):
    """A tiny page social sites can read (they ignore #/ routes), sending people on to the real page.

    `large` asks for a wide preview card, for landscape images (film backdrops).
    """
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}">
<meta property="og:site_name" content="Trailer Math"><meta property="og:type" content="article">
{f'<meta property="og:image" content="{esc(image)}">' if image else ""}<meta name="twitter:card" content="{"summary_large_image" if large else "summary"}">
<meta http-equiv="refresh" content="0;url={esc(target)}"><link rel="canonical" href="{esc(target)}"></head>
<body><a href="{esc(target)}">{esc(title)}</a></body></html>"""


def benchmark(films, today):
    """First-trailer lead time by primary genre, over films that have already opened."""
    by_genre = {}
    for f in films.values():
        lead = first_lead(f)
        if lead is not None and f["release"] <= str(today) and f["genre"]:
            by_genre.setdefault(f["genre"], []).append(lead)
    rows = []
    for genre, leads in by_genre.items():
        if len(leads) < 5:  # too few films for a median to mean anything
            continue
        q = statistics.quantiles(leads, n=4, method="inclusive")
        rows.append({"genre": genre, "n": len(leads), "median": round(statistics.median(leads)),
                     "p25": round(q[0]), "p75": round(q[2])})
    rows.sort(key=lambda r: -r["median"])
    every = [l for ls in by_genre.values() for l in ls]
    overall = {"n": len(every), "median": round(statistics.median(every))} if every else None
    return {"overall": overall, "genres": rows}


# ---------- fetching ----------

def kind(video):
    """TMDB files TV spots ("Tickets On Sale Now") under Teaser; the name tells them apart."""
    name = video["name"].lower()
    if "teaser" in name:
        return "Teaser"
    if "trailer" in name:
        return "Trailer"
    return "Spot"


def is_reissue(release, original, max_gap=180):
    """A US theatrical run long after the film's first release (Soul in 2024) isn't a new campaign."""
    return bool(original) and days_out(release, original) > max_gap


def film_from_tmdb(d):
    release = us_release(d.get("release_dates", {}))
    if release and is_reissue(release, d.get("release_date")):
        release = None
    videos = [{"key": v["key"], "type": kind(v), "name": v["name"], "published": v["published_at"]}
              for v in d.get("videos", {}).get("results", [])
              if v["site"] == "YouTube" and v.get("official") and v["type"] in CAMPAIGN_TYPES]
    return {
        "title": d["title"],
        "release": release,
        "genre": d["genres"][0]["name"] if d.get("genres") else None,
        "poster": d.get("poster_path"),
        "backdrop": d.get("backdrop_path"),
        "videos": sorted(videos, key=lambda v: v["published"]),
    }


def discover(start, end, pages):
    ids = []
    for page in range(1, pages + 1):
        res = tmdb("/discover/movie", region="US", with_release_type=3, sort_by="popularity.desc",
                   **{"release_date.gte": str(start), "release_date.lte": str(end)}, page=page)
        ids += [m["id"] for m in res["results"]]
        if page >= res["total_pages"]:
            break
    return ids


def refresh_films(films, ids, oldest):
    for i, mid in enumerate(dict.fromkeys(ids)):
        d = tmdb(f"/movie/{mid}", append_to_response="videos,release_dates", include_video_language="en")
        film = film_from_tmdb(d)
        if not film["release"]:  # no US wide release, or a reissue: drop anything stored from an earlier run
            films.pop(str(mid), None)
        elif film["release"] >= str(oldest):
            films[str(mid)] = keep_found(films.get(str(mid)), film)
        # else: opened before the searched window (Jaws matched via its 2025 anniversary run); leave history as is
        if i % 50 == 49:
            print(f"  {i + 1} films", flush=True)


def watch_channels(films, now):
    """Add new studio trailers straight from YouTube, so their first-day views are caught."""
    known = {v["key"] for f in films.values() for v in f["videos"]}
    since = now - timedelta(hours=CHANNEL_LOOKBACK_HOURS)
    found = 0
    for channel in STUDIO_CHANNELS:
        try:  # 1 quota unit each; one bad channel shouldn't stop the build
            res = get_json("https://www.googleapis.com/youtube/v3/playlistItems?" + urllib.parse.urlencode(
                {"part": "snippet", "playlistId": "UU" + channel[2:], "maxResults": 15,
                 "key": os.environ["YOUTUBE_API_KEY"]}))
        except urllib.error.HTTPError as e:
            print(f"  channel {channel}: {e}", file=sys.stderr)
            continue
        for item in res.get("items", []):
            s = item["snippet"]
            key, title = s["resourceId"]["videoId"], s["title"]
            if key in known or datetime.fromisoformat(s["publishedAt"].replace("Z", "+00:00")) < since:
                continue
            mid = match_upload(title, films, now.date())
            if mid and not is_reupload(films[mid], s["publishedAt"]):
                films[mid]["videos"].append({"key": key, "type": kind({"name": title}), "name": title,
                                             "published": s["publishedAt"], "found": "channel"})
                films[mid]["videos"].sort(key=lambda v: v["published"])
                known.add(key)
                found += 1
    return found


def snapshot_views(films, views, now):
    cutoff = now - timedelta(days=ACTIVE_DAYS)
    active = {v["key"]: v for f in films.values() for v in f["videos"]
              if datetime.fromisoformat(v["published"].replace("Z", "+00:00")) >= cutoff}
    keys = list(active)
    for i in range(0, len(keys), 50):  # 1 quota unit per call of up to 50 videos
        res = get_json("https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode(
            {"part": "statistics,snippet", "id": ",".join(keys[i:i + 50]), "key": os.environ["YOUTUBE_API_KEY"]}))
        for item in res.get("items", []):
            rec = views.setdefault(item["id"], {"snaps": [], "h24": None})
            stats = item["statistics"]
            rec["snaps"].append([now.isoformat(timespec="seconds"), int(stats.get("viewCount", 0))])
            # shortcut: latest counts only (frozen once the video is 30 days old); snapshot them if a 24h rate is needed.
            # None when the uploader hides likes or turns comments off.
            for field, name in (("likes", "likeCount"), ("comments", "commentCount")):
                rec[field] = int(stats[name]) if name in stats else None
            active[item["id"]]["published"] = item["snippet"]["publishedAt"]  # YouTube's time beats TMDB's
            active[item["id"]]["channel"] = item["snippet"]["channelTitle"]
    for key, rec in views.items():
        film_video = active.get(key)
        if film_video and rec["h24"] is None:
            rec["h24"] = views_at_24h(film_video["published"], rec["snaps"])
        # Raw counts are kept only while a video is young; the 24h figure is what stays.
        rec["snaps"] = [s for s in rec["snaps"] if datetime.fromisoformat(s[0]) >= cutoff]
    return len(keys)


def write_site(films, views, now):
    out = {}
    for mid, f in films.items():
        vids = []
        for v in f["videos"]:
            rec = views.get(v["key"], {})
            snaps = rec.get("snaps") or []
            vids.append({**v, "views": snaps[-1][1] if snaps else None, "h24": rec.get("h24"),
                         "likes": rec.get("likes"), "comments": rec.get("comments")})
        out[mid] = {**f, "videos": vids, "lead": first_lead(f)}
    posts = [p for f in sorted(POSTS.glob("*.md")) if (p := parse_post(f.read_text("utf-8"), f.stem))]
    posts.sort(key=lambda p: p["date"], reverse=True)
    data = {"updatedAt": now.isoformat(timespec="seconds"), "films": out,
            "benchmark": benchmark(films, now.date()), "posts": posts}
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    # Share pages: /f/<id>.html per film, /f/post-<slug>.html per post. Content is stable between runs,
    # so the hourly deploy only uploads pages that changed.
    SHARE.mkdir(exist_ok=True)
    for mid, f in films.items():
        lead = first_lead(f)
        desc = (f"US opening {f['release']}. " + (f"First teaser or trailer: {lead} days out." if lead is not None
                else "No official teaser or trailer yet.") + " Campaign timeline on Trailer Math.")
        poster = f"https://image.tmdb.org/t/p/w500{f['poster']}" if f.get("poster") else None
        (SHARE / f"{mid}.html").write_text(
            share_page(f"{f['title']}: the trailer campaign", desc, poster, f"{SITE}/#/film/{mid}"), "utf-8")
    for p in posts:
        film = films.get(p["film"] or "", {})
        image = (f"https://image.tmdb.org/t/p/w1280{film['backdrop']}" if film.get("backdrop")
                 else f"https://image.tmdb.org/t/p/w500{film['poster']}" if film.get("poster") else None)
        (SHARE / f"post-{p['slug']}.html").write_text(share_page(
            p["title"], p["summary"] or "From the Trailer Math blog.", image, f"{SITE}/#/blog/{p['slug']}",
            large=bool(film.get("backdrop"))), "utf-8")


def main():
    load_env()
    missing = [k for k in ("TMDB_TOKEN", "YOUTUBE_API_KEY") if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing {', '.join(missing)} (set them in the environment or in .env)")
    now = datetime.now(timezone.utc)
    today = now.date()
    films = json.loads(FILMS.read_text("utf-8")) if FILMS.exists() else {}
    views = json.loads(VIEWS.read_text("utf-8")) if VIEWS.exists() else {}

    oldest = today - timedelta(days=WINDOW_BACK)
    ids = discover(oldest, today + timedelta(days=WINDOW_AHEAD), CURRENT_PAGES)
    if "--backfill" in sys.argv:
        years = int(sys.argv[sys.argv.index("--backfill") + 1])
        for half in range(years * 2):  # half-year slices so popular films don't crowd out a whole year
            end = today - timedelta(days=WINDOW_BACK + 182 * half)
            ids += discover(end - timedelta(days=182), end, BACKFILL_PAGES)
            oldest = end - timedelta(days=182)
    print(f"refreshing {len(set(ids))} films", flush=True)
    refresh_films(films, ids, oldest)
    print(f"{watch_channels(films, now)} new trailers found on studio channels", flush=True)
    n = snapshot_views(films, views, now)

    FILMS.parent.mkdir(exist_ok=True)
    FILMS.write_text(json.dumps(films, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    VIEWS.write_text(json.dumps(views, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    write_site(films, views, now)
    print(f"{len(films)} films, {n} young videos snapshotted -> {OUT}")


if __name__ == "__main__":
    main()
