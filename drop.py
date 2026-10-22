"""Draft this week's issue of The Drop in Buttondown, from the live site's data.

    python drop.py           # print the issue
    python drop.py --draft   # also save it as a Buttondown draft (needs BUTTONDOWN_API_KEY)

It only ever creates a draft: you read it, edit it, and press send in Buttondown.
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

from build import SITE, load_env


def views(n):
    if n is None:
        return "—"
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}K" if n >= 1e3 else str(n)


def issue(data, now):
    """(subject, Markdown body) for the week ending now."""
    since, today = now - timedelta(days=7), now.date()
    drops = sorted(((f, v, mid) for mid, f in data["films"].items() for v in f["videos"]
                    if v["type"] != "Spot" and datetime.fromisoformat(v["published"].replace("Z", "+00:00")) >= since),
                   key=lambda d: d[1]["published"])
    # Only films with a campaign to speak of; the calendar also holds many with no official trailer.
    opening = sorted((f for f in data["films"].values() if f["videos"]
                      and today < date.fromisoformat(f["release"]) <= today + timedelta(days=7)), key=lambda f: f["release"])[:8]
    post = next((p for p in data.get("posts", []) if date.fromisoformat(p["date"]) >= since.date()), None)
    best = max((d for d in drops if d[1].get("h24")), key=lambda d: d[1]["h24"], default=None)

    lines = []
    if post:
        lines += [f"## {post['title']}", post["summary"], f"[Read it on the blog]({SITE}/#/blog/{post['slug']})", ""]
    lines += [f"## This week's drops ({len(drops)})"]
    for f, v, mid in drops:
        out = (date.fromisoformat(f["release"]) - date.fromisoformat(v["published"][:10])).days
        when = f"{out} days out" if out >= 0 else f"{-out} days after opening"
        first_day = f", {views(v['h24'])} views in its first 24 hours" if v.get("h24") else ""
        lines.append(f"- **[{f['title']}]({SITE}/#/film/{mid})**, {v['type'].lower()}: {when}{first_day}")
    if not drops:
        lines.append("No new official teasers or trailers this week.")
    if opening:
        lines += ["", "## Opening this week"]
        for f in opening:
            d = date.fromisoformat(f["release"])
            lines.append(f"- {f['title']} ({d:%a %b} {d.day})")
    lines += ["", f"[Every campaign on Trailer Math]({SITE})"]

    if best:
        subject = f"The Drop: {best[0]['title']} leads this week's trailers"
    else:
        subject = f"The Drop: {len(drops)} new trailer{'' if len(drops) == 1 else 's'} this week"
    return subject, "\n".join(lines)


def main():
    load_env()
    # Cloudflare's bot protection refuses Python's default user agent.
    req = urllib.request.Request(f"{SITE}/data.json", headers={"User-Agent": "TrailerMath-drop/1.0 (+https://trailermath.com)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    subject, body = issue(data, datetime.now(timezone.utc))
    print(subject, "\n", body, sep="\n")
    if "--draft" in sys.argv:
        req = urllib.request.Request(
            "https://api.buttondown.com/v1/emails", method="POST",
            data=json.dumps({"subject": subject, "body": body, "status": "draft"}).encode(),
            headers={"Authorization": f"Token {os.environ['BUTTONDOWN_API_KEY']}", "Content-Type": "application/json",
                     "X-API-Version": "2026-04-01"})
        with urllib.request.urlopen(req, timeout=30) as r:
            print("Buttondown draft created:", json.load(r).get("id"))


if __name__ == "__main__":
    main()
