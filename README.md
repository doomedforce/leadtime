# Trailer Math

How movies are marketed, trailer by trailer: every new official teaser and trailer, how many days
before opening it dropped, and how it did in its first 24 hours on YouTube. Campaign timelines per film
and first-trailer benchmarks by genre. Home: trailermath.com.

- `build.py`: pulls US wide releases from TMDB (60 days back to a year ahead), their official YouTube
  teasers and trailers, and hourly view counts from the YouTube Data API. Writes `public/data.json`.
- `data/`: committed state. `films.json` is every film seen so far (the benchmark's history);
  `views.json` holds view snapshots for videos under 30 days old and each video's 24-hour figure.
- `public/`: the static site (`#/` this week, `#/upcoming`, `#/benchmarks`, `#/film/<tmdb id>`).
- `.github/workflows/build.yml`: commits `data/` and deploys to Cloudflare Pages.
- `cron/`: a Cloudflare Worker (`trailermath-cron`) that starts the build at :11 every hour. GitHub's own
  schedule skips most hours, so it is only a 3-hourly fallback. The Worker needs a `GITHUB_TOKEN` secret
  (fine-grained, this repo only, "Actions: Read and write"). Redeploy with `cd cron && npm i && npx cf deploy`.
- New trailers are also read straight from 27 studio YouTube channels (`STUDIO_CHANNELS` in `build.py`),
  so a trailer is tracked within the hour it drops instead of whenever TMDB lists it.

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
- A 24-hour figure exists only when Trailer Math saw the video within its first day, with snapshots on
  both sides of the 24-hour mark no more than 12 hours apart.
- Trailers from studios outside `STUDIO_CHANNELS` are found through TMDB, usually within hours; one
  added late gets no 24-hour figure. A channel upload is matched by the film's title appearing in the
  video title, so titles under 4 characters are left to TMDB.
- "Genre" is the film's first-listed TMDB genre.
- YouTube's developer policies limit how long API data may be stored. Raw view snapshots are dropped
  after 30 days; check whether keeping the 24-hour figure longer is allowed before launch.
