"""Offline checks for build.py. Run: python test_build.py"""
from datetime import date

from build import (benchmark, days_out, film_from_tmdb, first_lead, is_reissue, is_reupload, keep_found, kind,
                   match_upload, md_to_html, parse_post, share_page, us_release, views_at_24h)

# Posts: the small Markdown subset, escaped, with only web and in-site links.
html = md_to_html("## Why now\n\nThe teaser is **101 days** out, *early* for\nhorror. [Film](#/film/1)\n\n- one\n- two <b>")
assert html == ('<h2>Why now</h2>\n<p>The teaser is <strong>101 days</strong> out, <em>early</em> for horror. '
                '<a href="#/film/1">Film</a></p>\n<ul><li>one</li><li>two &lt;b&gt;</li></ul>'), html
assert "href" not in md_to_html("[x](javascript:alert(1))")  # left as plain text, never a link
post = parse_post("---\ntitle: Slayground's early tease\ndate: 2026-10-23\nfilm: 123\n---\nBody.", "slayground")
assert post["title"] == "Slayground's early tease" and post["film"] == "123" and post["html"] == "<p>Body.</p>" and post["minutes"] == 1
assert parse_post("---\ntitle: T\ndate: 2026-10-23\ndraft: true\n---\nBody.", "x") is None
assert parse_post("---\ntitle: T\ndate: 2026-10-23\npublish: 2999-01-01T16:00:00Z\n---\nBody.", "x") is None
assert parse_post("---\ntitle: T\ndate: 2026-10-23\npublish: 2026-01-01T16:00:00Z\n---\nBody.", "x")
for bad in ("No front matter", "---\ntitle: T\ndate: someday\n---\nBody."):
    try:
        parse_post(bad, "x")
        raise AssertionError("bad post accepted")
    except (ValueError, KeyError):
        pass

# Share pages: titles are escaped, and the page sends people on to the real page.
page = share_page('A "Quoted" <Title>', "d", None, "https://trailermath.com/#/film/1")
assert "&quot;Quoted&quot; &lt;Title&gt;" in page and 'url=https://trailermath.com/#/film/1"' in page
assert "og:image" not in page

# The same trailer posted twice within minutes counts once; a new trailer days later counts.
rocky = {"videos": [{"published": "2026-10-22T16:00:00Z"}]}
assert is_reupload(rocky, "2026-10-22T16:00:05Z")
assert is_reupload(rocky, "2026-10-22T19:04:00Z")
assert not is_reupload(rocky, "2026-10-25T16:00:00Z")

# Studio uploads: matched by the film's title in the video title, longest title wins.
tracked = {"1": {"title": "Wicked", "release": "2026-11-20"},
           "2": {"title": "Wicked: For Good", "release": "2026-11-21"},
           "3": {"title": "Us", "release": "2026-12-01"},
           "4": {"title": "Old Film", "release": "2025-01-01"}}
today = date(2026, 10, 22)
assert match_upload("Wicked: For Good | Official Trailer 2", tracked, today) == "2"
assert match_upload("WICKED - Final Trailer", tracked, today) == "1"
assert match_upload("Wicked: For Good | Behind the Scenes", tracked, today) is None  # not a trailer
assert match_upload("Us | Official Trailer", tracked, today) is None  # too short to match safely
assert match_upload("Old Film | Anniversary Trailer", tracked, today) is None  # opened long ago
assert match_upload("Something Else | Official Trailer", tracked, today) is None

# A refresh from TMDB keeps channel-found videos TMDB hasn't listed yet, without duplicating ones it has.
old = {"videos": [{"key": "a", "published": "2026-10-01T00:00:00Z", "found": "channel"},
                  {"key": "b", "published": "2026-10-02T00:00:00Z", "found": "channel"},
                  {"key": "c", "published": "2026-09-01T00:00:00Z"}]}
new = {"title": "X", "videos": [{"key": "b", "published": "2026-10-02T00:00:00Z"}]}
assert [v["key"] for v in keep_found(old, new)["videos"]] == ["a", "b"]  # c was TMDB's and is gone from TMDB
assert keep_found(None, new) == new
# I Play Rocky: the channel caught one upload, TMDB later listed the studio's other upload 23 seconds apart.
old = {"videos": [{"key": "chan", "published": "2026-10-22T16:00:30Z", "found": "channel"}]}
new = {"videos": [{"key": "tmdb", "published": "2026-10-22T16:00:07Z"}, {"key": "t1", "published": "2026-07-15T13:00:51Z"}]}
assert [v["key"] for v in keep_found(old, new)["videos"]] == ["t1", "chan"]

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

# The Drop: this week's teasers and trailers (not spots), what opens in the next 7 days, the week's blog post.
from datetime import datetime, timezone
from drop import issue
week = {"films": {
    "1": {"title": "Slayground", "release": "2027-01-29", "videos": [
        {"type": "Teaser", "published": "2026-10-20T13:00:00Z", "h24": 1_500_000},
        {"type": "Spot", "published": "2026-10-21T13:00:00Z", "h24": None},
        {"type": "Trailer", "published": "2026-09-01T13:00:00Z", "h24": 5}]},
    "2": {"title": "Wicker", "release": "2026-10-23", "videos": [{"type": "Trailer", "published": "2026-08-01T00:00:00Z"}]},
    "3": {"title": "No Campaign", "release": "2026-10-23", "videos": []}},
    "posts": [{"slug": "s", "title": "Early tease", "summary": "Why now.", "date": "2026-10-21"}]}
subject, body = issue(week, datetime(2026, 10, 22, 18, tzinfo=timezone.utc))
assert subject == "The Drop: Slayground leads this week's trailers", subject
assert "## Early tease" in body and "1.5M views in its first 24 hours" in body and "101 days out" in body
assert body.count("Slayground") == 1  # the spot and the old trailer are left out
assert "- Wicker (Fri Oct 23)" in body and "No Campaign" not in body, body

# Weekly post helper: dated next Monday, a draft, the real numbers written out, prompts left for the author.
from new_post import draft_post
bench = {"genres": [{"genre": "Action", "n": 118, "median": 80, "p25": 45, "p75": 142}]}
slay = {"title": "Slayground", "release": "2027-01-29", "genre": "Action", "videos": [
    {"key": "p", "type": "Spot", "name": "Official Promo", "published": "2026-09-21T13:00:00Z"},
    {"key": "t", "type": "Teaser", "name": "Official Teaser", "published": "2026-10-20T13:00:00Z"}]}
name, text = draft_post("1442761", slay, {"t": {"h24": 1_400_000}}, bench, date(2026, 10, 22))
assert name == "2026-10-26-slayground.md", name
assert "draft: true" in text and "film: 1442761" in text
assert "**101 days** before its January 29 opening" in text
assert "21 days earlier than the median action campaign" in text and "inside the middle half" in text
assert "- Oct 20: Official Teaser (teaser, 101 days out, 1.4 million views in its first 24 hours)" in text
assert "[YOUR READ" in text
assert parse_post(text, "x") is None  # stays unpublished until the author removes draft: true

# Snapshots keep likes and comments; a hidden count stays None instead of 0.
import os
from datetime import datetime, timezone
import build
os.environ.setdefault("YOUTUBE_API_KEY", "test")
build.get_json = lambda url: {"items": [{"id": "k", "statistics": {"viewCount": "10", "likeCount": "3"},
                                         "snippet": {"publishedAt": "2026-10-22T16:00:00Z", "channelTitle": "A24"}}]}
snapped = {}
build.snapshot_views({"1": {"videos": [{"key": "k", "published": "2026-10-22T16:00:00Z"}]}}, snapped,
                     datetime(2026, 10, 23, tzinfo=timezone.utc))
assert snapped["k"]["snaps"][-1][1] == 10 and snapped["k"]["likes"] == 3 and snapped["k"]["comments"] is None

# A film TMDB lists but then 404s is skipped; stored films are kept.
import io, urllib.error
def fake_tmdb(path, **kw):
    if path == "/movie/404":
        raise urllib.error.HTTPError(path, 404, "Not Found", {}, io.BytesIO())
    raise AssertionError("only the missing film is fetched")
build.tmdb = fake_tmdb
kept = {"404": {"title": "Gone"}}
build.refresh_films(kept, [404], date(2026, 1, 1))
assert kept == {"404": {"title": "Gone"}}

print("ok")
