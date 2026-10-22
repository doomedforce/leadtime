const DAY = 864e5;
const TZ = "America/Los_Angeles"; // the industry's clock
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const views = (n) => (n == null ? `<span class="dash">—</span>` : compact.format(n));
const plural = (n, word) => `${n.toLocaleString("en-US")} ${word}${n === 1 ? "" : "s"}`;

// Release dates are calendar dates (no time zone); publish times are instants shown in LA time.
const thisYear = new Date().getFullYear();
const releaseFmt = (y) => new Intl.DateTimeFormat("en-US", { timeZone: "UTC", weekday: "short", month: "short", day: "numeric", ...(y ? { year: "numeric" } : {}) });
const opens = (d) => releaseFmt(+d.slice(0, 4) !== thisYear).format(new Date(d + "T00:00:00Z"));
const pubDate = new Intl.DateTimeFormat("en-US", { timeZone: TZ, month: "short", day: "numeric", year: "numeric" });
const pubShort = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "short", month: "short", day: "numeric" });
const clock = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" });
const laDate = (t) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(t); // YYYY-MM-DD

const daysBetween = (a, b) => Math.round((Date.parse(b + "T00:00:00Z") - Date.parse(a + "T00:00:00Z")) / DAY);
const daysOut = (film, video) => daysBetween(video.published.slice(0, 10), film.release);
const outText = (d) => d > 0 ? `${plural(d, "day")} out` : d === 0 ? "Opening day" : `${plural(-d, "day")} after opening`;
const thumb = (key) => `https://i.ytimg.com/vi/${encodeURIComponent(key)}/mqdefault.jpg`;
const youtube = (key) => `https://www.youtube.com/watch?v=${encodeURIComponent(key)}`;
const posterImg = (p, cls = "poster") => p ? `<img class="${cls}" src="https://image.tmdb.org/t/p/w185${esc(p)}" alt="" loading="lazy">` : `<div class="${cls}"></div>`;

let data, genreStats;

function vsMedian(film) {
  const g = genreStats[film.genre];
  if (film.lead == null || !g) return "";
  const diff = film.lead - g.median;
  if (Math.abs(diff) < 7) return `about the ${esc(film.genre)} median of ${plural(g.median, "day")}`;
  return `${plural(Math.abs(diff), "day")} ${diff > 0 ? "earlier" : "later"} than the ${esc(film.genre)} median of ${plural(g.median, "day")}`;
}

// ---------- This week: every official teaser and trailer from the last 7 days ----------
function weekView() {
  const since = Date.now() - 7 * DAY;
  const drops = Object.entries(data.films).flatMap(([id, film]) => film.videos
    .filter((v) => v.type !== "Spot" && Date.parse(v.published) >= since)
    .map((v) => ({ id, film, v, out: daysOut(film, v) })))
    .sort((a, b) => b.v.published.localeCompare(a.v.published));

  let finding = "No new official teasers or trailers in the last 7 days.";
  if (drops.length) {
    const best = drops.filter((d) => d.v.h24 != null).sort((a, b) => b.v.h24 - a.v.h24)[0];
    const earliest = [...drops].sort((a, b) => b.out - a.out)[0];
    const count = drops.length === 1 ? "1 new teaser or trailer" : `${drops.length} new teasers and trailers`;
    finding = `<strong class="num">${count}</strong> in the last 7 days. ` +
      (best ? `Biggest first day: ${esc(best.film.title)}, <span class="num">${compact.format(best.v.h24)}</span> views in 24 hours.`
            : `Furthest from opening: ${esc(earliest.film.title)}, ${outText(earliest.out).toLowerCase()}.`);
  }

  return `<div class="title-row"><h1>Trailer drops this week</h1><p class="finding">${finding}</p></div>
  ${drops.length ? `<table>
    <thead><tr><th>Video</th><th>Type</th><th class="num">Before opening</th><th class="num">First 24 h</th><th class="num">Views now</th><th class="num">Published</th></tr></thead>
    <tbody>${drops.map(({ id, film, v, out }) => `<tr>
      <td><div class="who"><a href="${youtube(v.key)}" target="_blank" rel="noopener" aria-label="Watch ${esc(v.name)} on YouTube"><img class="thumb" src="${thumb(v.key)}" alt="" loading="lazy"></a>
        <div><b><a href="#/film/${id}">${esc(film.title)}</a></b><span class="sub">${esc(v.name)}</span></div></div></td>
      <td><span class="pill">${esc(v.type)}</span></td>
      <td class="num lead-cell"><span class="big ${out > 0 ? "hue" : ""}">${out > 0 ? out : out === 0 ? "0" : `+${-out}`}</span><span class="sub">${out >= 0 ? "days out" : "days after opening"} · opens ${opens(film.release)}</span></td>
      <td class="num" data-k="First 24 h">${views(v.h24)}</td>
      <td class="num" data-k="Views now">${views(v.views)}</td>
      <td class="num" data-k="Published">${pubShort.format(new Date(v.published))}<span class="sub">${clock.format(new Date(v.published))} PT</span></td>
    </tr>`).join("")}</tbody></table>` : ""}`;
}

// ---------- Upcoming: films opening in the next 120 days and how their campaigns stand ----------
function upcomingView() {
  const today = laDate(new Date());
  const films = Object.entries(data.films)
    .filter(([, f]) => { const d = daysBetween(today, f.release); return d > 0 && d <= 120; })
    .sort((a, b) => a[1].release.localeCompare(b[1].release) || a[1].title.localeCompare(b[1].title));
  const silent = films.filter(([, f]) => !f.videos.length).length;
  return `<div class="title-row"><h1>Opening in the next 120 days</h1>
    <p class="finding"><strong class="num">${plural(films.length, "film")}</strong> on the US wide-release calendar${silent ? `, ${silent} with no official teaser or trailer yet` : ""}.</p></div>
  ${films.length ? `<table>
    <thead><tr><th>Film</th><th class="num">Opens</th><th class="num">Teasers and trailers</th><th class="num">First trailer</th></tr></thead>
    <tbody>${films.map(([id, f]) => `<tr>
      <td><div class="who">${posterImg(f.poster)}<div><b><a href="#/film/${id}">${esc(f.title)}</a></b><span class="sub">${esc(f.genre || "—")}</span></div></div></td>
      <td class="num">${opens(f.release)}<span class="sub">in ${plural(daysBetween(today, f.release), "day")}</span></td>
      <td class="num" data-k="Teasers and trailers">${f.videos.length || `<span class="dash">None yet</span>`}</td>
      <td class="num lead-cell">${f.lead != null ? `<span class="hue">${plural(f.lead, "day")} out</span><span class="sub">${vsMedian(f)}</span>` : `<span class="dash">—</span>`}</td>
    </tr>`).join("")}</tbody></table>` : `<p class="state">No films found for the next 120 days.</p>`}`;
}

// ---------- Film: the campaign as a strip toward opening day ----------
function strip(film) {
  const g = genreStats[film.genre];
  const today = laDate(new Date());
  const toOpen = daysBetween(today, film.release);
  const outs = film.videos.map((v) => daysOut(film, v));
  let step = Math.max(...outs, g?.p75 || 0, toOpen > 0 ? toOpen : 0, 30) > 240 ? 60 : 30;
  const max = Math.ceil(Math.max(...outs, g?.p75 || 0, toOpen, 30) / step) * step;
  const min = Math.min(0, ...outs);
  // Drawn at the strip's real width so 12px labels stay 12px on a phone; fewer ticks when narrow.
  const W = Math.max(300, Math.min(1072, $("view").clientWidth - 44)), P = 12, Y = 34;
  if (W < 600 && max / step > 4) step *= 2;
  const x = (d) => P + ((max - d) / (max - min || 1)) * (W - 2 * P);
  const ticks = [];
  for (let d = max; d > 0; d -= step) ticks.push(d);
  const marks = film.videos.map((v, i) => `<circle class="${v.type.toLowerCase()}" cx="${x(outs[i]).toFixed(1)}" cy="${Y}" r="${v.type === "Spot" ? 4 : 6}"><title>${esc(v.name)}: ${outText(outs[i])}</title></circle>`).join("");
  return `<div class="strip"><svg viewBox="0 0 ${W} 72" role="img" aria-label="Campaign timeline: ${film.videos.length} videos between ${max} days out and opening">
    ${g ? `<rect class="iqr" x="${x(g.p75)}" y="${Y - 9}" width="${x(g.p25) - x(g.p75)}" height="18" rx="3"/><line class="med" x1="${x(g.median)}" x2="${x(g.median)}" y1="${Y - 16}" y2="${Y + 16}"/>` : ""}
    <line class="axis" x1="${P}" x2="${W - P}" y1="${Y}" y2="${Y}"/>
    ${ticks.map((d) => `<g class="tick"><line x1="${x(d)}" x2="${x(d)}" y1="${Y + 8}" y2="${Y + 14}"/><text x="${x(d)}" y="${Y + 30}" text-anchor="${d === max ? "start" : "middle"}">${d} days</text></g>`).join("")}
    <g class="tick"><line x1="${x(0)}" x2="${x(0)}" y1="${Y - 12}" y2="${Y + 14}" style="stroke:var(--text)"/><text x="${x(0)}" y="${Y + 30}" text-anchor="${min < 0 ? "middle" : "end"}" style="fill:var(--text)">Opening</text></g>
    ${toOpen > 0 && toOpen < max ? `<line class="now" x1="${x(toOpen)}" x2="${x(toOpen)}" y1="${Y - 18}" y2="${Y + 6}"/><text class="lbl" x="${x(toOpen) + 5}" y="${Y - 10}">Today</text>` : ""}
    ${marks}
  </svg>
  <div class="key">
    <span><svg viewBox="0 0 12 12"><circle cx="6" cy="6" r="4" fill="none" stroke="var(--accent)" stroke-width="2"/></svg>Teaser</span>
    <span><svg viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="var(--accent)"/></svg>Trailer</span>
    ${film.videos.some((v) => v.type === "Spot") ? `<span><svg viewBox="0 0 12 12"><circle cx="6" cy="6" r="4" fill="var(--muted)"/></svg>Spot</span>` : ""}
    ${g ? `<span><svg viewBox="0 0 12 12"><rect y="2" width="12" height="8" rx="2" fill="var(--band)"/></svg>Middle half of ${esc(film.genre)} first trailers</span>
    <span><svg viewBox="0 0 12 12"><line x1="6" x2="6" y1="0" y2="12" stroke="var(--muted)" stroke-dasharray="3 3"/></svg>${esc(film.genre)} median</span>` : ""}
  </div></div>`;
}

function filmView(id) {
  const film = data.films[id];
  if (!film) return `<a class="back" href="#/">← This week</a><p class="state">We don't track that film.</p>`;
  const g = genreStats[film.genre];
  const today = laDate(new Date());
  const toOpen = daysBetween(today, film.release);
  const finding = film.lead != null
    ? `The first ${film.videos[0] && daysOut(film, film.videos[0]) === film.lead ? film.videos[0].type.toLowerCase() : "trailer"} landed ${plural(film.lead, "day")} before opening${vsMedian(film) ? `, ${vsMedian(film)}` : ""}.`
    : toOpen > 0 ? `No official teaser or trailer yet, ${plural(toOpen, "day")} before opening.` : "No official teaser or trailer on record.";
  return `<a class="back" href="#/">← This week</a>
  <div class="film-head">${posterImg(film.poster)}<div><h1>${esc(film.title)}</h1><p class="finding">${finding}</p></div></div>
  <dl class="facts">
    <div><dt>Opens in the US</dt><dd>${opens(film.release)} <small>${toOpen > 0 ? `in ${plural(toOpen, "day")}` : toOpen === 0 ? "today" : "opened"}</small></dd></div>
    <div><dt>First teaser or trailer</dt><dd>${film.lead != null ? `${film.lead} <small>days out</small>` : `<span class="dash">—</span>`}</dd></div>
    <div><dt>${esc(film.genre || "Genre")} median</dt><dd>${g ? `${g.median} <small>days out, ${plural(g.n, "film")}</small>` : `<span class="dash">—</span>`}</dd></div>
  </dl>
  ${film.videos.length ? `<section><h2 class="section-h">Campaign</h2>${strip(film)}
  <table>
    <thead><tr><th>Video</th><th class="num">Before opening</th><th class="num">First 24 h</th><th class="num">Views now</th><th class="num">Published</th></tr></thead>
    <tbody>${film.videos.map((v) => { const out = daysOut(film, v); return `<tr>
      <td><div class="who"><a href="${youtube(v.key)}" target="_blank" rel="noopener" aria-label="Watch ${esc(v.name)} on YouTube"><img class="thumb" src="${thumb(v.key)}" alt="" loading="lazy"></a>
        <div><b>${esc(v.name)}</b><span class="sub">${esc(v.type)}${v.channel ? ` · ${esc(v.channel)}` : ""}</span></div></div></td>
      <td class="num lead-cell"><span class="${out > 0 ? "hue" : ""}">${outText(out)}</span></td>
      <td class="num" data-k="First 24 h">${views(v.h24)}</td>
      <td class="num" data-k="Views now">${views(v.views)}</td>
      <td class="num" data-k="Published">${pubDate.format(new Date(v.published))}</td></tr>`; }).join("")}</tbody></table></section>` : ""}`;
}

// ---------- Benchmarks: how far out the first trailer lands, by genre ----------
function benchmarksView() {
  const b = data.benchmark;
  if (!b.genres.length) return `<div class="title-row"><h1>When the first trailer lands</h1></div><p class="state">Not enough released films yet to compare genres.</p>`;
  const top = Math.ceil(Math.max(...b.genres.map((g) => g.p75)) / 60) * 60;
  const pct = (d) => `${(d / top) * 100}%`;
  const ticks = []; for (let d = 0; d <= top; d += 60) ticks.push(d);
  const first = b.genres[0], last = b.genres[b.genres.length - 1];
  return `<div class="title-row"><h1>When the first trailer lands</h1>
    <p class="finding">Across <strong class="num">${plural(b.overall.n, "film")}</strong> released in the US, the first official teaser or trailer landed a median of <strong class="num">${plural(b.overall.median, "day")}</strong> before opening. ${esc(first.genre)} campaigns start earliest (median ${first.median} days); ${esc(last.genre)} campaigns start latest (${last.median} days).</p></div>
  <table class="bench">
    <thead><tr><th>Genre</th><th class="num">Films</th><th style="width:50%"><div class="scale">${ticks.map((d) => `<span style="left:${pct(d)}">${d}</span>`).join("")}</div></th><th class="num">Median</th></tr></thead>
    <tbody>${b.genres.map((g) => `<tr>
      <td><b>${esc(g.genre)}</b></td>
      <td class="num" data-k="Films">${g.n}</td>
      <td class="range-cell"><div class="range" role="img" aria-label="${esc(g.genre)}: middle half ${g.p75} to ${g.p25} days out, median ${g.median}">
        <div class="track"></div><div class="band" style="left:${pct(g.p25)};width:${pct(g.p75 - g.p25)}"></div><div class="median" style="left:${pct(g.median)}"></div></div></td>
      <td class="num"><span class="hue">${g.median}</span> <span class="dash">days</span></td></tr>`).join("")}</tbody></table>
  <p class="finding" style="margin-top:16px;font-size:13px">Each bar is the middle half of a genre's campaigns, by days from the first official teaser or trailer to US opening; the tick is the median. Genres need at least 5 released films to appear. A film counts under its first-listed TMDB genre.</p>`;
}

function render() {
  const [, route, id] = location.hash.split("/");
  const page = route === "upcoming" ? upcomingView() : route === "benchmarks" ? benchmarksView() : route === "film" ? filmView(id) : weekView();
  $("view").innerHTML = page;
  const nav = route === "film" ? null : route || "week";
  document.querySelectorAll("[data-nav]").forEach((a) =>
    a.dataset.nav === nav ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  const h1 = $("view").querySelector("h1");
  document.title = `${h1 ? h1.textContent + " — " : ""}Lead Time`;
  window.scrollTo(0, 0);
}

async function load() {
  try {
    const res = await fetch("/data.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(res.status);
    data = await res.json();
    genreStats = Object.fromEntries(data.benchmark.genres.map((g) => [g.genre, g]));
    const t = new Date(data.updatedAt);
    $("stamp").textContent = `Updated ${laDate(t) === laDate(new Date()) ? "" : pubShort.format(t) + ", "}${clock.format(t)} PT`;
    render();
  } catch {
    $("view").innerHTML = `<p class="state">Couldn't load campaign data. <a href="" style="text-decoration:underline">Retry</a></p>`;
  }
}

addEventListener("hashchange", () => data && render());
load();
