"""Offline checks for build.py. Run: python test_build.py"""
from datetime import date

from build import benchmark, days_out, film_from_tmdb, first_lead, is_reissue, kind, us_release, views_at_24h

# TV spots filed as teasers are told apart by name.
assert kind({"name": "Official Teaser Trailer"}) == "Teaser"
assert kind({"name": "Final Trailer"}) == "Trailer"
assert kind({"name": "Tickets On Sale Now"}) == "Spot"

# Soul: Disney+ in Dec 2020, US theaters Jan 2024. Not a new campaign.
assert is_reissue("2024-01-12", "2020-12-25")
assert not is_reissue("2026-07-17", "2026-07-10")  # opened abroad a week earlier: fine
assert not is_reissue("2026-07-17", None)

# US wide release (type 3) wins over premieres (1), limited (2) and other countries.
rd = {"results": [
    {"iso_3166_1": "GB", "release_dates": [{"type": 3, "release_date": "2026-07-10T00:00:00.000Z"}]},
    {"iso_3166_1": "US", "release_dates": [
        {"type": 1, "release_date": "2026-07-01T00:00:00.000Z"},
        {"type": 3, "release_date": "2026-07-17T00:00:00.000Z"},
        {"type": 2, "release_date": "2026-07-15T00:00:00.000Z"}]}]}
assert us_release(rd) == "2026-07-17"
assert us_release({"results": []}) is None

assert days_out("2026-07-17", "2026-03-19T16:00:00.000Z") == 120
assert days_out("2026-07-17", "2026-07-20T16:00:00.000Z") == -3

# Only official YouTube teasers and trailers count; clips and fan uploads don't.
d = {"title": "Example", "genres": [{"name": "Horror"}, {"name": "Thriller"}], "poster_path": "/p.jpg",
     "release_dates": rd, "videos": {"results": [
         {"key": "b", "site": "YouTube", "official": True, "type": "Trailer", "name": "Trailer", "published_at": "2026-05-01T16:00:00.000Z"},
         {"key": "a", "site": "YouTube", "official": True, "type": "Teaser", "name": "Teaser", "published_at": "2026-02-01T16:00:00.000Z"},
         {"key": "c", "site": "YouTube", "official": True, "type": "Clip", "name": "Clip", "published_at": "2026-06-01T16:00:00.000Z"},
         {"key": "d", "site": "YouTube", "official": False, "type": "Trailer", "name": "Fan cut", "published_at": "2025-01-01T16:00:00.000Z"},
         {"key": "e", "site": "Vimeo", "official": True, "type": "Trailer", "name": "Vimeo", "published_at": "2025-12-01T16:00:00.000Z"}]}}
film = film_from_tmdb(d)
assert film["genre"] == "Horror" and film["release"] == "2026-07-17"
assert film_from_tmdb({**d, "release_date": "2020-01-01"})["release"] is None  # reissue
assert [v["key"] for v in film["videos"]] == ["a", "b"]  # oldest first
assert first_lead(film) == 166  # Feb 1 to Jul 17

# A trailer re-uploaded after opening, or one dated years out, isn't the campaign's start.
odd = {"release": "2026-07-17", "videos": [{"published": "2026-08-01T00:00:00Z"}, {"published": "2021-01-01T00:00:00Z"}]}
assert first_lead(odd) is None

# 24h views: interpolate between the snapshots either side of publish + 24h.
pub = "2026-10-20T16:00:00Z"
snaps = [["2026-10-21T15:00:00+00:00", 1_000_000], ["2026-10-21T17:00:00+00:00", 1_200_000]]
assert views_at_24h(pub, snaps) == 1_100_000
assert views_at_24h(pub, snaps[:1]) is None  # nothing after the 24h mark yet
assert views_at_24h(pub, [["2026-10-22T16:00:00+00:00", 5]]) is None  # found it too late
gappy = [["2026-10-21T00:00:00+00:00", 1], ["2026-10-21T20:00:00+00:00", 2]]
assert views_at_24h(pub, gappy) is None  # 20h apart is too coarse to call it a 24h figure

# Benchmark: per primary genre, released films only, at least 5 films per genre.
def f(genre, release, lead_days):
    pub = date.fromordinal(date.fromisoformat(release).toordinal() - lead_days).isoformat()
    return {"genre": genre, "release": release, "videos": [{"published": pub + "T00:00:00Z"}]}

films = {str(i): f("Horror", "2026-01-01", lead) for i, lead in enumerate([60, 90, 100, 120, 200])}
films["x"] = f("Animation", "2026-01-01", 300)  # only one: left out of the genre rows
films["y"] = f("Horror", "2027-01-01", 10)  # not open yet: left out
b = benchmark(films, date(2026, 10, 22))
assert [r["genre"] for r in b["genres"]] == ["Horror"]
assert b["genres"][0] == {"genre": "Horror", "n": 5, "median": 100, "p25": 90, "p75": 120}
assert b["overall"] == {"n": 6, "median": 110}

print("ok")
