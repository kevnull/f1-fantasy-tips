"""
render.py — Generate docs/index.html from strategy JSON + OpenF1 photos + weather + circuit map.
"""

import json, base64, re, urllib.request
from datetime import datetime
from pathlib import Path

OPENF1_DRIVERS_URL = "https://api.openf1.org/v1/drivers?session_key=latest"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.formula1.com/",
}
BASE_GEO = "https://raw.githubusercontent.com/bacinger/f1-circuits/master/circuits"

# race_name_lower → {lat, lng, geo: bacinger circuit ID}
CIRCUIT_DATA = {
    "bahrain":        {"lat": 26.032, "lng":  50.511, "geo": "bh-2002"},
    "saudi arabia":   {"lat": 21.632, "lng":  39.104, "geo": "sa-2021"},
    "australia":      {"lat":-37.850, "lng": 144.968, "geo": "au-1953"},
    "japan":          {"lat": 34.844, "lng": 136.541, "geo": "jp-1962"},
    "china":          {"lat": 31.340, "lng": 121.220, "geo": "cn-2004"},
    "miami":          {"lat": 25.958, "lng": -80.239, "geo": "us-2022"},
    "emilia romagna": {"lat": 44.341, "lng":  11.713, "geo": "it-1953"},
    "imola":          {"lat": 44.341, "lng":  11.713, "geo": "it-1953"},
    "monaco":         {"lat": 43.734, "lng":   7.421, "geo": "mc-1929"},
    "spain":          {"lat": 41.570, "lng":   2.261, "geo": "es-2026"},
    "canada":         {"lat": 45.505, "lng": -73.527, "geo": "ca-1978"},
    "austria":        {"lat": 47.220, "lng":  14.760, "geo": "at-1969"},
    "great britain":  {"lat": 52.079, "lng":  -1.017, "geo": "gb-1948"},
    "hungary":        {"lat": 47.583, "lng":  19.249, "geo": "hu-1986"},
    "belgium":        {"lat": 50.437, "lng":   5.974, "geo": "be-1925"},
    "netherlands":    {"lat": 52.388, "lng":   4.540, "geo": "nl-1948"},
    "italy":          {"lat": 45.621, "lng":   9.281, "geo": "it-1953"},
    "azerbaijan":     {"lat": 40.373, "lng":  49.853, "geo": "az-2016"},
    "singapore":      {"lat":  1.291, "lng": 103.864, "geo": "sg-2008"},
    "united states":  {"lat": 30.133, "lng": -97.641, "geo": "us-2012"},
    "mexico":         {"lat": 19.404, "lng": -99.091, "geo": "mx-1962"},
    "brazil":         {"lat":-23.701, "lng": -46.697, "geo": "br-1977"},
    "las vegas":      {"lat": 36.114, "lng":-115.173, "geo": "us-2023"},
    "qatar":          {"lat": 25.490, "lng":  51.454, "geo": "qa-2004"},
    "abu dhabi":      {"lat": 24.467, "lng":  54.603, "geo": "ae-2009"},
}

# WMO weather code → condition slug
def wmo_cond(code) -> str:
    if code is None: return "clear"
    c = int(code)
    if c == 0:              return "clear"
    if c in (1, 2):         return "partly"
    if c == 3:              return "cloudy"
    if c in (45, 48):       return "foggy"
    if 51 <= c <= 67:       return "rain"
    if 71 <= c <= 77:       return "snow"
    if 80 <= c <= 82:       return "showers"
    if 85 <= c <= 86:       return "snow"
    if 95 <= c <= 99:       return "thunder"
    return "clear"

WEATHER_LABELS = {
    "clear": "Clear", "partly": "Partly cloudy", "cloudy": "Overcast",
    "foggy": "Foggy", "rain": "Rain", "snow": "Snow",
    "showers": "Showers", "thunder": "Thunderstorm",
}

WEATHER_ICONS = {
    "clear":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><line x1="12" y1="2" x2="12" y2="4.5"/><line x1="12" y1="19.5" x2="12" y2="22"/><line x1="2" y1="12" x2="4.5" y2="12"/><line x1="19.5" y1="12" x2="22" y2="12"/><line x1="5.64" y1="5.64" x2="7.05" y2="7.05"/><line x1="16.95" y1="16.95" x2="18.36" y2="18.36"/><line x1="5.64" y1="18.36" x2="7.05" y2="16.95"/><line x1="16.95" y1="7.05" x2="18.36" y2="5.64"/></svg>',
    "partly":  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="9" r="3"/><line x1="10" y1="3" x2="10" y2="5"/><line x1="16.24" y1="5.76" x2="14.83" y2="7.17"/><path d="M20 15h-1a5 5 0 0 0-9.9-1H7a4 4 0 0 0 0 8h13a3 3 0 0 0 0-6h-.1z" opacity=".7"/></svg>',
    "cloudy":  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/></svg>',
    "foggy":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/><line x1="4" y1="19" x2="20" y2="19"/><line x1="4" y1="22" x2="14" y2="22"/></svg>',
    "rain":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 17.58A5 5 0 0 0 18 8h-1.26A8 8 0 1 0 4 16.25"/><line x1="8" y1="19" x2="8" y2="21"/><line x1="8" y1="13" x2="8" y2="15"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="12" y1="17" x2="12" y2="19"/><line x1="16" y1="19" x2="16" y2="21"/></svg>',
    "showers": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/><line x1="8" y1="19" x2="8" y2="21"/><line x1="12" y1="17" x2="12" y2="19"/><line x1="16" y1="19" x2="16" y2="21"/></svg>',
    "snow":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="2" x2="12" y2="22"/><path d="m20 17-8-5-8 5"/><path d="m20 7-8 5-8-5"/></svg>',
    "thunder": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M19 16.9A5 5 0 0 0 18 7h-1.26a8 8 0 1 0-11.62 9"/><polyline points="13 11 9 17 15 17 11 23"/></svg>',
}

CHIP_ICONS = {
    "wildcard":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/></svg>',
    "limitless":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 12c-2-2.5-4-4-6-4a4 4 0 0 0 0 8c2 0 4-1.5 6-4z"/><path d="M12 12c2 2.5 4 4 6 4a4 4 0 0 0 0-8c-2 0-4 1.5-6 4z"/></svg>',
    "no_negative": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>',
    "final_fix":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    "extra_drs":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
    "autopilot":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>',
}

def chip_icon(name: str) -> str:
    n = name.lower()
    key = None
    if "wild" in n:              key = "wildcard"
    elif "limit" in n:           key = "limitless"
    elif "negat" in n:           key = "no_negative"
    elif "final" in n or "fix" in n: key = "final_fix"
    elif "drs" in n or "extra" in n: key = "extra_drs"
    elif "auto" in n or "pilot" in n: key = "autopilot"
    return f'<span class="chip-icon">{CHIP_ICONS[key]}</span>' if key and key in CHIP_ICONS else ""

def lookup_circuit(name: str) -> dict | None:
    k = name.lower().strip()
    if k in CIRCUIT_DATA: return CIRCUIT_DATA[k]
    for ck, cv in CIRCUIT_DATA.items():
        if ck in k or k in ck: return cv
    return None

def fmt_date(iso: str) -> str:
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%a %-d %b")
    except: return iso[:10]

# ── Circuit map ────────────────────────────────────────────────────────────────

def geojson_to_svg(geo: dict) -> str:
    coords = None
    for feat in geo.get("features", []):
        if feat["geometry"]["type"] == "LineString":
            coords = feat["geometry"]["coordinates"]
            break
    if not coords: return ""

    lngs = [c[0] for c in coords]
    lats  = [c[1] for c in coords]
    mnx, mxx = min(lngs), max(lngs)
    mny, mxy = min(lats),  max(lats)
    lngr = mxx - mnx or 0.001
    latr = mxy - mny or 0.001

    VW, VH, PAD = 560, 180, 18
    scale = min((VW - 2*PAD) / lngr, (VH - 2*PAD) / latr)
    tw, th = lngr * scale, latr * scale
    xo, yo = (VW - tw) / 2, (VH - th) / 2

    pts = [f"{(lng-mnx)*scale+xo:.2f},{(mxy-lat)*scale+yo:.2f}" for lng, lat in coords]
    d = "M " + " L ".join(pts)
    return (f'<svg class="circuit-svg" viewBox="0 0 {VW} {VH}" xmlns="http://www.w3.org/2000/svg">'
            f'<path d="{d}" fill="none" stroke="currentColor" stroke-width="4" '
            f'stroke-linecap="round" stroke-linejoin="round"/></svg>')

CIRCUIT_CACHE_DIR = Path("data/cache/circuits")
PHOTO_CACHE_DIR = Path("data/cache/photos")


def fetch_circuit_svg(race_name: str) -> str:
    c = lookup_circuit(race_name)
    if not c or not c.get("geo"): return ""
    cache_file = CIRCUIT_CACHE_DIR / f"{c['geo']}.svg"
    if cache_file.exists():
        svg = cache_file.read_text()
        print(f"  [circuit] {c['geo']} (cached) → {len(svg)} chars")
        return svg
    url = f"{BASE_GEO}/{c['geo']}.geojson"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "f1-fantasy-tips/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            geo = json.load(r)
        svg = geojson_to_svg(geo)
        CIRCUIT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(svg)
        print(f"  [circuit] {c['geo']} (fetched, cached) → {len(svg)} chars")
        return svg
    except Exception as e:
        print(f"  [circuit] Failed {c['geo']}: {e}")
        return ""

# ── Weather ────────────────────────────────────────────────────────────────────

def fetch_session_weather(race_name: str, season: int) -> dict:
    result = {"qualifying": None, "race": None}
    c = lookup_circuit(race_name)
    if not c: return result
    lat, lng = c["lat"], c["lng"]
    try:
        url = f"https://api.openf1.org/v1/meetings?year={season}"
        req = urllib.request.Request(url, headers={"User-Agent": "f1-fantasy-tips/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            meetings = json.load(r)

        rl = race_name.lower()
        meeting = next(
            (m for m in meetings if rl in m.get("meeting_name","").lower()
             or rl in m.get("location","").lower()
             or rl in m.get("circuit_short_name","").lower()),
            None
        )
        if not meeting:
            print(f"  [weather] No meeting: {race_name}")
            return result

        url2 = f"https://api.openf1.org/v1/sessions?meeting_key={meeting['meeting_key']}"
        with urllib.request.urlopen(urllib.request.Request(url2, headers={"User-Agent": "f1-fantasy-tips/1.0"}), timeout=10) as r:
            sessions = json.load(r)

        quali = next((s for s in sessions if s.get("session_type","").lower() == "qualifying"), None)
        race  = next((s for s in sessions if s.get("session_type","").lower() == "race"), None)

        dates = {d for d in [
            quali["date_start"][:10] if quali else None,
            race["date_start"][:10]  if race  else None
        ] if d}
        if not dates: return result

        wurl = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}"
                f"&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
                f"&timezone=auto&start_date={min(dates)}&end_date={max(dates)}")
        with urllib.request.urlopen(wurl, timeout=10) as r:
            wd = json.load(r)

        daily = wd.get("daily", {})
        by_date = {}
        for i, d in enumerate(daily.get("time", [])):
            by_date[d] = {
                "date": d,
                "code":  (daily.get("weathercode") or [None]*99)[i],
                "tmax":  (daily.get("temperature_2m_max") or [None]*99)[i],
                "tmin":  (daily.get("temperature_2m_min") or [None]*99)[i],
                "precip":(daily.get("precipitation_probability_max") or [None]*99)[i],
            }

        if quali: result["qualifying"] = by_date.get(quali["date_start"][:10])
        if race:  result["race"]       = by_date.get(race["date_start"][:10])
        print(f"  [weather] Fetched quali={result['qualifying'] and result['qualifying']['date']} "
              f"race={result['race'] and result['race']['date']}")
    except Exception as e:
        print(f"  [weather] Error: {e}")
    return result

def weather_cell(label: str, data: dict | None) -> str:
    if not data:
        return f'<div class="wx-cell"><div class="wx-label">{label}</div><div class="wx-empty">—</div></div>'
    cond   = wmo_cond(data.get("code"))
    icon   = WEATHER_ICONS.get(cond, WEATHER_ICONS["clear"])
    tmax   = f'{round(data["tmax"])}°' if data.get("tmax") is not None else "—"
    tmin   = f'{round(data["tmin"])}°' if data.get("tmin") is not None else ""
    precip = f'{round(data["precip"])}%' if data.get("precip") is not None else ""
    wlabel = WEATHER_LABELS.get(cond, cond)
    date_s = fmt_date(data.get("date",""))
    precip_html = f'<span class="wx-precip">💧 {precip}</span>' if precip else ""
    return f"""<div class="wx-cell">
      <div class="wx-label">{label}</div>
      <div class="wx-date">{date_s}</div>
      <div class="wx-main">
        <span class="wx-icon">{icon}</span>
        <span class="wx-temp">{tmax}</span>
        <span class="wx-cond">{wlabel}</span>
      </div>
      {precip_html}
    </div>"""

# ── Existing helpers ───────────────────────────────────────────────────────────

def fetch_photos(acronyms: list[str]) -> dict[str, str]:
    photos: dict[str, str] = {}
    missing: list[str] = []
    for acr in acronyms:
        cache_file = PHOTO_CACHE_DIR / acr
        if cache_file.exists():
            photos[acr] = cache_file.read_text()
        else:
            missing.append(acr)

    if not missing:
        print(f"Driver photos: {len(photos)} cached, 0 fetched")
        return photos

    print(f"Driver photos: {len(photos)} cached, fetching {len(missing)}: {missing}")
    req = urllib.request.Request(OPENF1_DRIVERS_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        drivers = {d["name_acronym"]: d for d in json.load(r)}
    PHOTO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for acr in missing:
        d = drivers.get(acr)
        if not d or not d.get("headshot_url"):
            photos[acr] = ""; continue
        try:
            req2 = urllib.request.Request(d["headshot_url"], headers=HEADERS)
            with urllib.request.urlopen(req2, timeout=10) as r2:
                data = r2.read()
                ct = r2.headers.get("Content-Type", "image/png").split(";")[0].strip()
                uri = f"data:{ct};base64,{base64.b64encode(data).decode()}"
            (PHOTO_CACHE_DIR / acr).write_text(uri)
            photos[acr] = uri
            print(f"  {acr}: {len(data)}B (cached)")
        except Exception as e:
            print(f"  {acr}: {e}"); photos[acr] = ""
    return photos

def avatar(acr: str, colour: str, photo: str, size: int) -> str:
    c = colour.lstrip("#") or "888888"
    fb = f'<span class="av-fb" style="width:{size}px;height:{size}px;background:#{c}">{acr}</span>'
    if not photo: return fb
    return (f'<img class="av" style="width:{size}px;height:{size}px" src="{photo}" alt="{acr}" '
            f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">{fb}')

def rec_cls(rec: str) -> str:
    return {"use": "rec-use", "save": "rec-save", "maybe": "rec-maybe"}.get(rec.lower(), "rec-save")

# ── Main render ────────────────────────────────────────────────────────────────

def render(strategy: dict, output_path: str = None) -> str:
    btier    = strategy.get("btier", {})
    captains = strategy.get("captains", [])
    race     = strategy.get("race", "F1 Fantasy")
    season   = strategy.get("season", "")

    all_acrs = list(dict.fromkeys(
        [c["acronym"] for c in captains] +
        [d["acronym"] for d in btier.get("buy", [])] +
        [d["acronym"] for d in btier.get("consider", [])]
    ))
    photos      = fetch_photos(all_acrs)
    circuit_svg = fetch_circuit_svg(race)
    weather     = fetch_session_weather(race, season)

    def captain_cards() -> str:
        html = ""
        for i, c in enumerate(captains):
            acr, col = c.get("acronym",""), c.get("team_colour","888888")
            border = "border:1.5px solid #B5D4F4" if i == 0 else "border:0.5px solid #e0e0e0"
            html += f"""<div class="captain-card" style="{border}">
              <div class="captain-card-label">{c.get('label','')}</div>
              <div class="captain-layout">
                <div class="captain-photo-wrap" style="border-color:#{col.lstrip('#')}">
                  {avatar(acr, col, photos.get(acr,''), 56)}
                </div>
                <div class="captain-info">
                  <div class="captain-name">{c.get('name','')}</div>
                  <div class="captain-price">{c.get('price','')} · {c.get('team','')}</div>
                  <div class="captain-reason">{c.get('reason','')}</div>
                </div>
              </div>
            </div>"""
        return html

    def pill_row(label_cls, label, drivers, pill_cls):
        pills = ""
        for d in drivers:
            acr, col = d.get("acronym",""), d.get("team_colour","888888")
            note = f'<span class="pill-note">{d["note"]}</span>' if d.get("note") else ""
            pills += f'<span class="pill {pill_cls}">{avatar(acr, col, photos.get(acr,""), 22)}{d.get("name",acr)} {d.get("price","")}{note}</span>'
        return f'<div class="driver-group"><div class="driver-group-label {label_cls}">{label}</div><div class="pills">{pills}</div></div>'

    def avoid_row():
        pills = "".join(f'<span class="pill pill-avoid">{n}</span>' for n in btier.get("avoid", []))
        return f'<div class="driver-group"><div class="driver-group-label label-avoid">Avoid</div><div class="pills">{pills}</div></div>'

    def chip_cards():
        html = ""
        for chip in strategy.get("chips", []):
            rec = chip.get("rec","save")
            label = "Wait" if rec == "maybe" else rec.capitalize()
            icon_html = chip_icon(chip.get("name",""))
            html += f'<div class="chip-card"><div class="chip-header"><span class="chip-name-wrap">{icon_html}<span class="chip-name">{chip.get("name","")}</span></span><span class="chip-rec {rec_cls(rec)}">{label}</span></div><div class="chip-body">{chip.get("reason","")}</div></div>'
        return html

    def watch_items():
        return "".join(f'<div class="watch-item"><div class="watch-dot"></div><div>{i}</div></div>' for i in strategy.get("watch_items", []))

    def sources():
        return "".join(f'<div class="source-item"><span class="source-channel">{s.get("channel","")}</span><a class="source-link" href="{s.get("url","#")}" target="_blank">{s.get("title","")}</a></div>' for s in strategy.get("sources", []))

    def budget_rows():
        rows = ""
        for t in strategy.get("meta_template", {}).get("budget_tiers", []):
            opt = '<span class="optimal-badge">optimal</span>' if t.get("optimal") else ""
            cls = ' class="highlight-row"' if t.get("optimal") else ""
            rows += f'<tr{cls}><td class="budget-val">{t["budget"]}{opt}</td><td>{t["core"]}</td><td>{t["fills"]}</td></tr>'
        return rows

    sprint_badge = '<span class="badge badge-sprint">Sprint weekend</span>' if strategy.get("sprint") else ""
    dl = strategy.get("deadline", "")
    dl_badge = f'<span class="badge badge-deadline">Deadline: {dl}</span>' if dl else ""
    updated  = datetime.utcnow().strftime("%-d %b %Y")
    meta_name = strategy.get("meta_template", {}).get("name", "")
    arc       = strategy.get("arc", "")
    arc_title = arc.split("—")[0].strip() if "—" in arc else "Race arc"

    circuit_section = (f'<div class="circuit-wrap" title="{race} circuit">{circuit_svg}</div>'
                       if circuit_svg else "")

    weather_section = ""
    if weather.get("qualifying") or weather.get("race"):
        weather_section = f"""<div class="wx-strip">
          {weather_cell("Qualifying", weather.get("qualifying"))}
          <div class="wx-divider"></div>
          {weather_cell("Race", weather.get("race"))}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>F1 Fantasy — {race} {season}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Helvetica,Arial,sans-serif;background:#fff;color:#111;padding:1.25rem;-webkit-font-smoothing:antialiased}}
@media(prefers-color-scheme:dark){{body{{background:#111;color:#f0f0f0}}}}
.page{{max-width:680px;margin:0 auto}}
a{{color:#185FA5;text-decoration:none}}
/* Header */
.header{{display:flex;align-items:flex-start;justify-content:space-between;padding-bottom:1rem;border-bottom:.5px solid #e0e0e0;margin-bottom:1rem}}
@media(prefers-color-scheme:dark){{.header{{border-color:#333}}}}
.race-title{{font-size:22px;font-weight:500;letter-spacing:-.02em}}
.race-meta{{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}}
.badge{{font-size:11px;font-weight:500;padding:3px 8px;border-radius:6px;border:.5px solid}}
.badge-sprint{{background:#FAEEDA;color:#633806;border-color:#FAC775}}
.badge-deadline{{background:#E6F1FB;color:#0C447C;border-color:#B5D4F4}}
.badge-round{{background:#f5f5f5;color:#555;border-color:#ddd}}
@media(prefers-color-scheme:dark){{.badge-round{{background:#222;color:#aaa;border-color:#444}}}}
.updated{{font-size:12px;color:#888;white-space:nowrap;padding-top:3px}}
/* Circuit map */
.circuit-wrap{{margin-bottom:1rem;display:flex;justify-content:center;align-items:center;height:130px;color:#bbb;padding:0 1rem}}
@media(prefers-color-scheme:dark){{.circuit-wrap{{color:#444}}}}
.circuit-svg{{height:100%;max-width:100%}}
/* Weather strip */
.wx-strip{{display:flex;border:.5px solid #e0e0e0;border-radius:10px;overflow:hidden;margin-bottom:1.25rem}}
@media(prefers-color-scheme:dark){{.wx-strip{{border-color:#333}}}}
.wx-cell{{flex:1;padding:.75rem 1rem}}
.wx-divider{{width:.5px;background:#e0e0e0;flex-shrink:0}}
@media(prefers-color-scheme:dark){{.wx-divider{{background:#333}}}}
.wx-label{{font-size:10px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:.07em;margin-bottom:3px}}
.wx-date{{font-size:12px;color:#888;margin-bottom:6px}}
.wx-main{{display:flex;align-items:center;gap:8px;margin-bottom:4px}}
.wx-icon{{width:22px;height:22px;flex-shrink:0;color:#555}}
@media(prefers-color-scheme:dark){{.wx-icon{{color:#aaa}}}}
.wx-icon svg{{width:100%;height:100%}}
.wx-temp{{font-size:17px;font-weight:600;letter-spacing:-.01em}}
.wx-cond{{font-size:12px;color:#888}}
.wx-precip{{font-size:12px;color:#5B8DD9}}
.wx-empty{{font-size:20px;color:#ccc;padding-top:6px}}
/* Callout */
.callout{{background:#fafafa;border-left:3px solid #EF9F27;border-radius:0 6px 6px 0;padding:.75rem 1rem;margin-bottom:1.25rem}}
@media(prefers-color-scheme:dark){{.callout{{background:#1a1a1a}}}}
.callout-label{{font-size:11px;font-weight:600;color:#633806;letter-spacing:.05em;text-transform:uppercase;margin-bottom:4px}}
.callout-text{{font-size:13.5px;line-height:1.55}}
/* Sections */
.section{{margin-bottom:1.5rem}}
.section-title{{font-size:11px;font-weight:600;color:#888;letter-spacing:.07em;text-transform:uppercase;margin-bottom:.75rem;padding-bottom:.4rem;border-bottom:.5px solid #e0e0e0}}
@media(prefers-color-scheme:dark){{.section-title{{border-color:#333}}}}
/* Budget table */
.budget-table{{width:100%;font-size:13px;border-collapse:collapse}}
.budget-table th{{font-weight:500;color:#888;text-align:left;padding:6px 8px;border-bottom:.5px solid #e0e0e0;font-size:12px}}
@media(prefers-color-scheme:dark){{.budget-table th{{border-color:#333}}}}
.budget-table td{{padding:7px 8px;border-bottom:.5px solid #e0e0e0;vertical-align:top;line-height:1.4}}
@media(prefers-color-scheme:dark){{.budget-table td{{border-color:#333}}}}
.budget-table tr:last-child td{{border-bottom:none}}
.budget-val{{font-weight:600;font-size:13.5px;white-space:nowrap}}
.highlight-row td{{background:rgba(100,160,255,.07)}}
.optimal-badge{{font-size:10px;background:#E6F1FB;color:#0C447C;padding:2px 6px;border-radius:4px;margin-left:6px;font-weight:600;vertical-align:middle}}
/* Captains */
.captain-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.captain-card{{border-radius:10px;padding:1rem 1.1rem;display:flex;flex-direction:column;gap:10px}}
@media(prefers-color-scheme:dark){{.captain-card{{background:#1a1a1a;border-color:#333!important}}}}
.captain-card-label{{font-size:10px;font-weight:600;color:#999;text-transform:uppercase;letter-spacing:.07em}}
.captain-layout{{display:flex;gap:12px;align-items:flex-start}}
.captain-photo-wrap{{flex-shrink:0;width:56px;height:56px;border-radius:50%;overflow:hidden;border-width:2.5px;border-style:solid;background:#f5f5f5;display:flex;align-items:center;justify-content:center}}
.captain-photo-wrap .av{{width:100%;height:100%;object-fit:cover;object-position:top center}}
.captain-photo-wrap .av-fb{{width:100%;height:100%;font-size:12px}}
.captain-info{{flex:1;min-width:0}}
.captain-name{{font-size:16px;font-weight:600;margin-bottom:2px;letter-spacing:-.01em}}
.captain-price{{font-size:12px;color:#888;margin-bottom:6px}}
.captain-reason{{font-size:12.5px;line-height:1.5}}
/* Avatars */
.av{{border-radius:50%;object-fit:cover;object-position:top center;display:block;flex-shrink:0}}
.av-fb{{border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:700;color:#fff;flex-shrink:0;letter-spacing:.02em}}
/* Pills */
.driver-groups{{display:flex;flex-direction:column;gap:10px}}
.driver-group{{display:flex;align-items:flex-start;gap:10px}}
.driver-group-label{{font-size:10px;font-weight:600;width:58px;flex-shrink:0;padding-top:6px;text-transform:uppercase;letter-spacing:.06em}}
.label-buy{{color:#3B6D11}}.label-consider{{color:#633806}}.label-avoid{{color:#A32D2D}}
.pills{{display:flex;flex-wrap:wrap;gap:6px}}
.pill{{font-size:12.5px;padding:5px 10px 5px 5px;border-radius:20px;border:.5px solid;line-height:1.35;display:inline-flex;align-items:center;gap:6px}}
.pill-avoid{{padding:5px 10px}}
.pill-buy{{background:#EAF3DE;color:#27500A;border-color:#C0DD97}}
.pill-consider{{background:#FAEEDA;color:#633806;border-color:#FAC775}}
.pill-avoid{{background:#FCEBEB;color:#791F1F;border-color:#F7C1C1}}
.pill-note{{font-size:11px;opacity:.7}}
/* Chips */
.chip-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.chip-card{{background:#fff;border:.5px solid #e0e0e0;border-radius:10px;padding:.85rem 1rem}}
@media(prefers-color-scheme:dark){{.chip-card{{background:#1a1a1a;border-color:#333}}}}
.chip-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:5px}}
.chip-name-wrap{{display:flex;align-items:center;gap:7px}}
.chip-icon{{width:17px;height:17px;flex-shrink:0;color:#666;display:flex}}
@media(prefers-color-scheme:dark){{.chip-icon{{color:#aaa}}}}
.chip-icon svg{{width:100%;height:100%}}
.chip-name{{font-size:13.5px;font-weight:600}}
.chip-rec{{font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;letter-spacing:.03em;white-space:nowrap}}
.rec-use{{background:#EAF3DE;color:#27500A}}.rec-save{{background:#E6F1FB;color:#0C447C}}.rec-maybe{{background:#FAEEDA;color:#633806}}
.chip-body{{font-size:12px;color:#666;line-height:1.5}}
@media(prefers-color-scheme:dark){{.chip-body{{color:#aaa}}}}
/* Watch list */
.watch-list{{display:flex;flex-direction:column}}
.watch-item{{display:flex;gap:10px;font-size:13px;line-height:1.55;padding:8px 0;border-bottom:.5px solid #e0e0e0}}
@media(prefers-color-scheme:dark){{.watch-item{{border-color:#333}}}}
.watch-item:last-child{{border-bottom:none}}
.watch-dot{{width:6px;height:6px;border-radius:50%;background:#EF9F27;flex-shrink:0;margin-top:7px}}
/* Arc */
.arc-text{{font-size:13px;line-height:1.6;background:#fafafa;border-radius:10px;padding:.9rem 1rem}}
@media(prefers-color-scheme:dark){{.arc-text{{background:#1a1a1a}}}}
/* Sources */
.sources-list{{display:flex;flex-direction:column}}
.source-item{{display:flex;align-items:baseline;gap:8px;font-size:12px;color:#888;padding:4px 0;border-bottom:.5px solid #e0e0e0}}
@media(prefers-color-scheme:dark){{.source-item{{border-color:#333}}}}
.source-item:last-child{{border-bottom:none}}
.source-channel{{font-weight:600;color:#111;min-width:130px;flex-shrink:0}}
@media(prefers-color-scheme:dark){{.source-channel{{color:#f0f0f0}}}}
.source-link{{color:#185FA5}}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <div>
      <div class="race-title">{race} {season}</div>
      <div class="race-meta">
        <span class="badge badge-round">Round {strategy.get('round','')}</span>
        {sprint_badge}{dl_badge}
      </div>
    </div>
    <div class="updated">Updated {updated}</div>
  </div>
  {circuit_section}
  {weather_section}
  <div class="callout">
    <div class="callout-label">Central unknown</div>
    <div class="callout-text">{strategy.get('central_unknown','')}</div>
  </div>
  <div class="section">
    <div class="section-title">Meta template — {meta_name}</div>
    <table class="budget-table">
      <thead><tr><th>Budget</th><th>Core</th><th>B-tier fills</th></tr></thead>
      <tbody>{budget_rows()}</tbody>
    </table>
  </div>
  <div class="section">
    <div class="section-title">×2 Captain</div>
    <div class="captain-grid">{captain_cards()}</div>
  </div>
  <div class="section">
    <div class="section-title">B-tier drivers</div>
    <div class="driver-groups">
      {pill_row("label-buy","Buy",btier.get("buy",[]),"pill-buy")}
      {pill_row("label-consider","Consider",btier.get("consider",[]),"pill-consider")}
      {avoid_row()}
    </div>
  </div>
  <div class="section">
    <div class="section-title">Chip strategy</div>
    <div class="chip-grid">{chip_cards()}</div>
  </div>
  <div class="section">
    <div class="section-title">Watch before deadline</div>
    <div class="watch-list">{watch_items()}</div>
  </div>
  <div class="section">
    <div class="section-title">{arc_title}</div>
    <div class="arc-text">{arc}</div>
  </div>
  <div class="section">
    <div class="section-title">Sources</div>
    <div class="sources-list">{sources()}</div>
  </div>
</div>
</body>
</html>"""

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"Written: {out} ({len(html):,} chars)")
    return html


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "data/strategy.json"
    dst = sys.argv[2] if len(sys.argv) > 2 else "docs/index.html"
    with open(src) as f:
        strategy = json.load(f)
    html = render(strategy)
    out = Path(dst)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Written: {out} ({len(html):,} chars)")
