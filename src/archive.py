"""
archive.py — Persist each race's strategy and re-render historical pages.

Layout on disk:
    data/archive/{season}-{slug}.json   committed strategy snapshots
    docs/index.html                     latest race
    docs/{season}/{slug}/index.html     per-race archive pages
    docs/archive.html                   index listing all archived races
"""

import json
import re
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from render import render

ARCHIVE_DIR = Path("data/archive")
DOCS_DIR    = Path("docs")
ARCHIVE_INDEX = DOCS_DIR / "archive.html"

MONTH_ABBREV = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# OpenF1 returns FIA/IOC-style 3-letter codes; regional indicator emoji need ISO alpha-2.
ALPHA3_TO_ALPHA2 = {
    "AUS": "AU", "CHN": "CN", "JPN": "JP", "BRN": "BH", "SAU": "SA",
    "USA": "US", "CAN": "CA", "MON": "MC", "ESP": "ES", "AUT": "AT",
    "GBR": "GB", "BEL": "BE", "HUN": "HU", "NED": "NL", "ITA": "IT",
    "AZE": "AZ", "SGP": "SG", "MEX": "MX", "BRA": "BR", "QAT": "QA",
    "UAE": "AE", "FRA": "FR", "GER": "DE", "TUR": "TR", "POR": "PT",
    "RUS": "RU", "MAL": "MY", "VIE": "VN",
}

_MEETINGS_CACHE: dict[int, list[dict]] = {}


def _openf1_meetings(season: int) -> list[dict]:
    if season in _MEETINGS_CACHE:
        return _MEETINGS_CACHE[season]
    try:
        req = urllib.request.Request(
            f"https://api.openf1.org/v1/meetings?year={season}",
            headers={"User-Agent": "f1-fantasy-tips/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            meetings = json.load(r)
    except Exception as e:
        print(f"  [archive] OpenF1 meetings fetch failed for {season}: {e}")
        meetings = []
    _MEETINGS_CACHE[season] = meetings
    return meetings


def _match_meeting(race_name: str, meetings: list[dict]) -> dict | None:
    """Find the OpenF1 meeting for a race by loose substring match."""
    key = re.sub(r"\b(grand prix|gp)\b", "", race_name.lower()).strip()
    key = re.sub(r"-", " ", key)
    toks = key.split()
    # Full-string, then all-tokens, then any-token (first match wins).
    for m in meetings:
        hay = f"{(m.get('meeting_name') or '').lower()}|{(m.get('location') or '').lower()}"
        if key and key in hay:
            return m
    for m in meetings:
        hay = f"{(m.get('meeting_name') or '').lower()}|{(m.get('location') or '').lower()}"
        if toks and all(t in hay for t in toks):
            return m
    for m in meetings:
        hay = f"{(m.get('meeting_name') or '').lower()}|{(m.get('location') or '').lower()}"
        if any(t in hay for t in toks if len(t) > 3):
            return m
    return None


def _flag(country_code: str | None) -> str:
    """Country code (2- or 3-letter) -> 🇺🇸 style emoji. Empty on unknown/bad input."""
    if not country_code: return ""
    cc = country_code.upper()
    if len(cc) == 3:
        cc = ALPHA3_TO_ALPHA2.get(cc, "")
    if len(cc) != 2 or not cc.isalpha():
        return ""
    return chr(0x1F1E6 + ord(cc[0]) - ord("A")) + chr(0x1F1E6 + ord(cc[1]) - ord("A"))


def _short_date(iso: str) -> str:
    """'2026-05-24T14:00:00+00:00' -> 'May 24, 2026'. Empty on parse failure."""
    if not iso: return ""
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            d = date.fromisoformat(iso[:10])
        except ValueError:
            return ""
    return f"{MONTH_ABBREV[d.month]} {d.day}, {d.year}"


def slug(race_name: str) -> str:
    """'Miami GP' -> 'miami-gp', 'Emilia Romagna' -> 'emilia-romagna'."""
    s = race_name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def archive_path(season: int, race_name: str) -> Path:
    return ARCHIVE_DIR / f"{season}-{slug(race_name)}.json"


def save(strategy: dict) -> Path:
    """Write strategy to data/archive/{season}-{slug}.json. Returns the path."""
    season = strategy.get("season") or 2026
    race   = strategy.get("race", "unknown")
    p = archive_path(season, race)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(strategy, indent=2))
    return p


def list_archive() -> list[dict]:
    """Returns archived strategies sorted newest-first by actual race date (from OpenF1)."""
    if not ARCHIVE_DIR.exists(): return []
    entries = []
    for f in ARCHIVE_DIR.glob("*.json"):
        try:
            s = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        season = s.get("season") or 2026
        race = s.get("race", f.stem)
        meeting = _match_meeting(race, _openf1_meetings(season))
        # OpenF1's date_start is FP1; race day is ~+2 (or +1 for sprint weekends).
        # For display purposes it's close enough; for sorting we want the FP1 date.
        date_start = (meeting or {}).get("date_start") or ""
        country_code = (meeting or {}).get("country_code") or ""
        entries.append({
            "season":   season,
            "round":    s.get("round") or 0,
            "race":     race,
            "deadline": s.get("deadline", ""),
            "slug":     slug(race),
            "path":     f,
            "date":     _short_date(date_start),
            "sort_key": date_start or "0000",
            "flag":     _flag(country_code),
        })
    entries.sort(key=lambda e: (e["season"], e["sort_key"]), reverse=True)
    return entries


def archive_html_path(season: int, race_slug: str) -> Path:
    return DOCS_DIR / str(season) / race_slug / "index.html"


def render_archive_pages(force: bool = False) -> int:
    """Render every archived strategy to docs/{season}/{slug}/index.html if the
    JSON is newer than the HTML (or force=True). Returns count of rendered pages."""
    n = 0
    for e in list_archive():
        out = archive_html_path(e["season"], e["slug"])
        if not force and out.exists() and out.stat().st_mtime >= e["path"].stat().st_mtime:
            continue
        strategy = json.loads(e["path"].read_text())
        render(strategy, output_path=str(out), is_archive=True)
        n += 1
    return n


def render_index() -> Path:
    """Generate docs/archive.html listing every archived race."""
    entries = list_archive()
    rows = ""
    for e in entries:
        href = f"{e['season']}/{e['slug']}/"
        flag = f'<span class="ar-flag">{e["flag"]}</span>' if e["flag"] else ""
        meta = e["date"] or f'{e["season"]}'
        rows += (
            f'<a class="ar-row" href="{href}">'
            f'{flag}'
            f'<span class="ar-race">{e["race"]}</span>'
            f'<span class="ar-meta">{meta}</span>'
            f'</a>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>F1 Fantasy — All races</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Helvetica,Arial,sans-serif;background:#fff;color:#111;padding:1.25rem;line-height:1.4;-webkit-font-smoothing:antialiased}}
@media(prefers-color-scheme:dark){{body{{background:#0a0a0a;color:#f0f0f0}}}}
.page{{max-width:680px;margin:0 auto}}
.title{{font-size:24px;font-weight:600;letter-spacing:-.02em;margin-bottom:.25rem}}
.subtitle{{font-size:13px;color:#888;margin-bottom:1.5rem}}
.back{{display:inline-block;font-size:12px;color:#888;text-decoration:none;margin-bottom:1rem}}
.back:hover{{color:#333}}
@media(prefers-color-scheme:dark){{.back:hover{{color:#fff}}}}
.ar-row{{display:flex;align-items:baseline;gap:.75rem;padding:.85rem 1rem;border:.5px solid #e0e0e0;border-radius:10px;margin-bottom:6px;text-decoration:none;color:inherit;transition:background .1s}}
.ar-row:hover{{background:#fafafa}}
@media(prefers-color-scheme:dark){{.ar-row{{border-color:#333}} .ar-row:hover{{background:#1a1a1a}}}}
.ar-flag{{font-size:18px;line-height:1;min-width:22px;text-align:center}}
.ar-race{{font-size:15px;font-weight:600;flex:1}}
.ar-meta{{font-size:11.5px;color:#888;white-space:nowrap}}
.empty{{font-size:13px;color:#888;text-align:center;padding:2rem 0}}
</style></head><body><div class="page">
<a class="back" href="./">← Latest race</a>
<div class="title">All races</div>
<div class="subtitle">{len(entries)} archived race{'s' if len(entries) != 1 else ''}</div>
{rows or '<div class="empty">No archived races yet.</div>'}
</div></body></html>"""

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_INDEX.write_text(html)
    return ARCHIVE_INDEX


def render_all() -> None:
    """Render every archive page + the index."""
    n = render_archive_pages()
    p = render_index()
    print(f"Archive: rendered {n} race page(s); index → {p}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        # Seed from current data/strategy.json
        s = json.loads(Path("data/strategy.json").read_text())
        p = save(s)
        print(f"Seeded archive: {p}")
    render_all()
