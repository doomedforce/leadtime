"""Start this week's blog post from a film's real campaign numbers.

    python new_post.py              # suggest films: this week's teasers and trailers, biggest first day first
    python new_post.py 1442761      # write posts/<next Monday>-<film>.md as a draft, facts filled in

The draft has the numbers; the [YOUR READ] parts are yours. Delete `draft: true` to publish.
"""
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone

from build import FILMS, POSTS, VIEWS, benchmark, days_out, first_lead

AUTHOR = ""  # your byline, e.g. "Jane Doe"; shown on every post


def fmt_views(n):
    return f"{n / 1e6:.1f} million" if n >= 1e6 else f"{n:,}"


def draft_post(mid, film, views, bench, today):
    """(file name, Markdown) for a draft post about one film."""
    monday = today + timedelta(days=(7 - today.weekday()) % 7)
    slug = re.sub(r"[^a-z0-9]+", "-", film["title"].lower()).strip("-")
    opens = date.fromisoformat(film["release"])
    g = next((r for r in bench["genres"] if r["genre"] == film["genre"]), None)
    campaign = [v for v in film["videos"] if v.get("type") != "Spot"]
    lead = first_lead(film)

    lines = []
    if lead is not None:
        first = next(v for v in campaign if days_out(film["release"], v["published"]) == lead)
        when = date.fromisoformat(first["published"][:10])
        lines.append(f"The first official {first['type'].lower()} for *{film['title']}* arrived on "
                     f"{when:%B} {when.day}, **{lead} days** before its {opens:%B} {opens.day} opening.")
        if g:
            diff = lead - g["median"]
            side = "earlier" if diff > 0 else "later"
            inside = g["p25"] <= lead <= g["p75"]
            lines[-1] += (f" That's {abs(diff)} days {side} than the median {film['genre'].lower()} campaign on "
                          f"Trailer Math ({g['median']} days, across {g['n']} released films), "
                          f"{'inside' if inside else 'outside'} the middle half of {film['genre'].lower()} rollouts "
                          f"({g['p25']} to {g['p75']} days out).")
    else:
        lines.append(f"*{film['title']}* opens {opens:%B} {opens.day} with no official teaser or trailer yet.")

    beats = []
    for v in film["videos"]:
        d = date.fromisoformat(v["published"][:10])
        out = days_out(film["release"], v["published"])
        rec = views.get(v["key"], {})
        h24 = f", {fmt_views(rec['h24'])} views in its first 24 hours" if rec.get("h24") else ""
        beats.append(f"- {d:%b} {d.day}: {v['name']} ({v['type'].lower()}, {out} days out{h24})")

    body = "\n\n".join([
        " ".join(lines),
        "## The campaign so far", "\n".join(beats) or "- Nothing yet.",
        "## What it's selling",
        "[YOUR READ: what do the teaser and trailer reveal and hold back? Who are they selling to? "
        "What's the one image or line people will remember?]",
        "## How it's doing",
        "[YOUR READ: are the first-day numbers above strong for this studio and genre? "
        "Compare one or two similar films on Trailer Math.]",
        "## What to watch",
        "- [YOUR CALL: the next beat you expect, or what you'd do differently.]",
        f"[Full campaign timeline](#/film/{mid})",
    ])
    front = "\n".join(["---", f"title: [YOUR HEADLINE] {film['title']}", f"date: {monday}", f"film: {mid}",
                       "summary: [ONE SENTENCE: the post's argument]", f"author: {AUTHOR}", "draft: true", "---"])
    return f"{monday}-{slug}.md", front + "\n" + body + "\n"


def suggest(films, views, now):
    since = now - timedelta(days=7)
    rows = [(views.get(v["key"], {}).get("h24") or 0, mid, f["title"], v["name"])
            for mid, f in films.items() for v in f["videos"]
            if v.get("type") != "Spot" and datetime.fromisoformat(v["published"].replace("Z", "+00:00")) >= since]
    for h24, mid, title, name in sorted(rows, reverse=True):
        print(f"{mid:>9}  {title}  |  {name}  |  first 24h: {fmt_views(h24) if h24 else 'not yet'}")


def main():
    films = json.loads(FILMS.read_text("utf-8"))
    views = json.loads(VIEWS.read_text("utf-8"))
    now = datetime.now(timezone.utc)
    if len(sys.argv) < 2:
        print("This week's teasers and trailers. Start a post with: python new_post.py <id>\n")
        return suggest(films, views, now)
    mid = sys.argv[1]
    if mid not in films:
        sys.exit(f"no tracked film with TMDB id {mid}")
    name, text = draft_post(mid, films[mid], views, benchmark(films, now.date()), now.date())
    path = POSTS / name
    if path.exists():
        sys.exit(f"{path} already exists")
    POSTS.mkdir(exist_ok=True)
    path.write_text(text, "utf-8")
    print(f"Started {path}. Fill in the [YOUR ...] parts, then delete `draft: true` to publish.")


if __name__ == "__main__":
    main()
