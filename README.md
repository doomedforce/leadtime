# Lead Time

How movies are marketed, trailer by trailer: every new official teaser and trailer, how many days
before opening it dropped, and how it did in its first 24 hours on YouTube. Campaign timelines per film
and first-trailer benchmarks by genre. Planned home: leadtime.film.

- `build.py`: pulls US wide releases from TMDB (60 days back to a year ahead), their official YouTube
  teasers and trailers, and hourly view counts from the YouTube Data API. Writes `public/data.json`.
- `data/`: committed state. `films.json` is every film seen so far (the benchmark's history);
  `views.json` holds view snapshots for videos under 30 days old and each video's 24-hour figure.
- `public/`: the static site (`#/` this week, `#/upcoming`, `#/benchmarks`, `#/film/<tmdb id>`).
- `.github/workflows/build.yml`: runs hourly, commits `data/`, deploys to Cloudflare Pages.

## Keys

Both are free:

- **TMDB:** create an account at themoviedb.org, then Settings → API. Copy the "API Read Access Token".
- **YouTube:** in Google Cloud Console, create a project, enable "YouTube Data API v3", and create an
  API key. Restrict it to that API.

For local runs, put them in a `.env` file here (it's gitignored):

```
TMDB_TOKEN=...
YOUTUBE_API_KEY=...
```

For the hourly build, add `TMDB_TOKEN`, `YOUTUBE_API_KEY`, `CLOUDFLARE_API_TOKEN` and
`CLOUDFLARE_ACCOUNT_ID` as GitHub Actions secrets.

## Run

```bash
python test_build.py
python build.py --backfill 3   # first run: also loads 3 years of releases for the benchmark
python build.py                # every run after that
python -m http.server 8766 --directory public
```

## Limits

- Views are official YouTube uploads only. Studio "24-hour" claims add up every platform and channel.
- A 24-hour figure exists only when Lead Time saw the video within its first day, with snapshots on
  both sides of the 24-hour mark no more than 12 hours apart.
- New trailers are found through TMDB, which its community updates, usually within hours. A trailer
  added late gets no 24-hour figure. The upgrade is polling the studios' YouTube channels directly.
- "Genre" is the film's first-listed TMDB genre.
- YouTube's developer policies limit how long API data may be stored. Raw view snapshots are dropped
  after 30 days; check whether keeping the 24-hour figure longer is allowed before launch.
