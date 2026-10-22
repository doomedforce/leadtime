"""Build Lead Time's data: film campaigns from TMDB, trailer views from YouTube.

    python build.py                  # refresh current films, snapshot views, write public/data.json
    python build.py --backfill 3     # also load the last 3 years of releases (for the benchmark)

Needs TMDB_TOKEN (TMDB "API Read Access Token") and YOUTUBE_API_KEY, from the environment or a .env file.
State lives in data/ and is committed, so view history survives between runs.
"""
import json
import os
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
VIEWS = ROOT / "data" / "views.json"  # {youtube key: {"snaps": [[iso, views]], "h24": int | None}}
OUT = ROOT / "public" / "data.json"

WINDOW_BACK, WINDOW_AHEAD = 60, 365  # days around today for "current" films
CURRENT_PAGES = 10                   # 20 films a page, most popular first
BACKFILL_PAGES = 8                   # per half year
ACTIVE_DAYS = 30                     # snapshot views for videos this young; also the snapshot retention
CAMPAIGN_TYPES = {"Teaser", "Trailer"}
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
            films[str(mid)] = film
        # else: opened before the searched window (Jaws matched via its 2025 anniversary run); leave history as is
        if i % 50 == 49:
            print(f"  {i + 1} films", flush=True)


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
            rec["snaps"].append([now.isoformat(timespec="seconds"), int(item["statistics"].get("viewCount", 0))])
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
            vids.append({**v, "views": snaps[-1][1] if snaps else None, "h24": rec.get("h24")})
        out[mid] = {**f, "videos": vids, "lead": first_lead(f)}
    data = {"updatedAt": now.isoformat(timespec="seconds"), "films": out,
            "benchmark": benchmark(films, now.date())}
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")


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
    n = snapshot_views(films, views, now)

    FILMS.parent.mkdir(exist_ok=True)
    FILMS.write_text(json.dumps(films, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    VIEWS.write_text(json.dumps(views, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    write_site(films, views, now)
    print(f"{len(films)} films, {n} young videos snapshotted -> {OUT}")


if __name__ == "__main__":
    main()
