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

SESSION_LABELS = {
    "practice 1":     "FP1",
    "practice 2":     "FP2",
    "practice 3":     "FP3",
    "sprint qualifying": "Sprint Quali",
    "sprint shootout": "Sprint Shootout",
    "sprint":         "Sprint",
    "qualifying":     "Qualifying",
    "race":           "Race",
}


def fetch_session_weather(race_name: str, season: int) -> list[dict]:
    """Returns a list of {label, date, code, tmax, tmin, precip} for every session of the meeting,
    in chronological order. Empty list on failure."""
    c = lookup_circuit(race_name)
    if not c: return []
    lat, lng = c["lat"], c["lng"]
    try:
        url = f"https://api.openf1.org/v1/meetings?year={season}"
        req = urllib.request.Request(url, headers={"User-Agent": "f1-fantasy-tips/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            meetings = json.load(r)

        # Normalize: strip "GP", "Grand Prix" so "Miami GP" matches "Miami Grand Prix"
        rl = re.sub(r"\b(grand prix|gp)\b", "", race_name.lower()).strip()
        meeting = next(
            (m for m in meetings if rl and (
                rl in m.get("meeting_name","").lower()
                or rl in m.get("location","").lower()
                or rl in m.get("circuit_short_name","").lower())),
            None
        )
        if not meeting:
            print(f"  [weather] No meeting: {race_name}")
            return []

        url2 = f"https://api.openf1.org/v1/sessions?meeting_key={meeting['meeting_key']}"
        with urllib.request.urlopen(urllib.request.Request(url2, headers={"User-Agent": "f1-fantasy-tips/1.0"}), timeout=10) as r:
            sessions = json.load(r)

        sessions = sorted(sessions, key=lambda s: s.get("date_start",""))
        if not sessions: return []

        dates = sorted({s["date_start"][:10] for s in sessions if s.get("date_start")})
        wurl = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}"
                f"&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
                f"&timezone=auto&start_date={dates[0]}&end_date={dates[-1]}")
        with urllib.request.urlopen(wurl, timeout=10) as r:
            wd = json.load(r)

        daily = wd.get("daily", {})
        by_date = {}
        for i, d in enumerate(daily.get("time", [])):
            by_date[d] = {
                "code":   (daily.get("weathercode") or [None]*99)[i],
                "tmax":   (daily.get("temperature_2m_max") or [None]*99)[i],
                "tmin":   (daily.get("temperature_2m_min") or [None]*99)[i],
                "precip": (daily.get("precipitation_probability_max") or [None]*99)[i],
            }

        forecasts = []
        for s in sessions:
            stype = (s.get("session_name") or s.get("session_type") or "").lower()
            label = SESSION_LABELS.get(stype) or stype.title()
            d = (s.get("date_start") or "")[:10]
            wx = by_date.get(d, {})
            forecasts.append({"label": label, "date": d, **wx})
        print(f"  [weather] {len(forecasts)} sessions: {[f['label'] for f in forecasts]}")
        return forecasts
    except Exception as e:
        print(f"  [weather] Error: {e}")
        return []

def weather_cell(forecast: dict) -> str:
    label  = forecast.get("label","")
    code   = forecast.get("code")
    cond   = wmo_cond(code) if code is not None else None
    icon   = WEATHER_ICONS.get(cond, WEATHER_ICONS["clear"]) if cond else ""
    tmax   = f'{round(forecast["tmax"])}°' if forecast.get("tmax") is not None else ""
    precip = forecast.get("precip")
    precip_html = f'<span class="wx-precip">💧 {round(precip)}%</span>' if precip is not None and precip >= 20 else ""
    iso = forecast.get("date","")
    try: date_s = datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%a")
    except: date_s = iso[:10]
    icon_html = f'<span class="wx-icon">{icon}</span>' if icon else '<span class="wx-icon"></span>'
    return f"""<div class="wx-cell">
      <div class="wx-label">{label}</div>
      <div class="wx-date">{date_s}</div>
      {icon_html}
      <div class="wx-temp">{tmax}</div>
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
    if not photo:
        return f'<span class="av-fb" style="width:{size}px;height:{size}px;background:#{c}">{acr}</span>'
    fb_hidden = f'<span class="av-fb" style="width:{size}px;height:{size}px;background:#{c};display:none">{acr}</span>'
    return (f'<img class="av" style="width:{size}px;height:{size}px" src="{photo}" alt="{acr}" '
            f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">{fb_hidden}')

def rec_cls(rec: str) -> str:
    return {"use": "rec-use", "save": "rec-save", "maybe": "rec-maybe"}.get(rec.lower(), "rec-save")

# ── Main render ────────────────────────────────────────────────────────────────

def render(strategy: dict, output_path: str = None, is_archive: bool = False) -> str:
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
        for c in captains:
            acr, col = c.get("acronym",""), c.get("team_colour","888888")
            tc = col.lstrip('#')
            html += f"""<div class="captain-card">
              <div class="captain-team-bar" style="background:#{tc}"></div>
              <div class="captain-body">
              <div class="captain-card-label">{c.get('label','')}</div>
              <div class="captain-layout">
                <div class="captain-photo-wrap" style="border-color:#{tc}">
                  {avatar(acr, col, photos.get(acr,''), 52)}
                </div>
                <div class="captain-info">
                  <div class="captain-name">{c.get('name','')}</div>
                  <div class="captain-price">{c.get('price','')} · {c.get('team','')}</div>
                  <div class="captain-reason">{c.get('reason','')}</div>
                </div>
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
        chip_colors = {"use": "#1A7C2E", "save": "#0044AA", "maybe": "#9B5500"}
        for chip in strategy.get("chips", []):
            rec = chip.get("rec","save")
            label = "Wait" if rec == "maybe" else rec.capitalize()
            icon_html = chip_icon(chip.get("name",""))
            color = chip_colors.get(rec, "#E4E4E4")
            html += f'<div class="chip-card" style="--chip-color:{color}"><div class="chip-header"><span class="chip-name-wrap">{icon_html}<span class="chip-name">{chip.get("name","")}</span></span><span class="chip-rec {rec_cls(rec)}">{label}</span></div><div class="chip-body">{chip.get("reason","")}</div></div>'
        return html

    def watch_items():
        return "".join(f'<div class="watch-item"><div class="watch-num">{n}</div><div>{item}</div></div>' for n, item in enumerate(strategy.get("watch_items", []), 1))

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

    from overtakes import lookup_rank
    overtake = lookup_rank(race)
    overtake_badge = ""
    if overtake:
        title = f'Avg {overtake["avg"]:.0f} overtakes per race since 2017 (racingpass.net)'
        overtake_badge = (f'<span class="badge badge-overtake" title="{title}">'
                          f'Overtakes #{overtake["rank"]}/{overtake["total"]}</span>')
    updated  = datetime.utcnow().strftime("%-d %b %Y")
    meta_name = strategy.get("meta_template", {}).get("name", "")
    arc       = strategy.get("arc", "")
    arc_title = "Race arc"

    circuit_html = f'<div class="circuit-wrap">{circuit_svg}</div>' if circuit_svg else ""
    weather_html = ""
    if weather:
        cells = "".join(weather_cell(f) for f in weather)
        weather_html = f'<div class="wx-strip">{cells}</div>'
    circuit_weather_section = (f'<div class="circuit-weather">{circuit_html}{weather_html}</div>'
                               if (circuit_html or weather_html) else "")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>F1 Fantasy — {race} {season}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Helvetica,Arial,sans-serif;background:#F2F2F2;color:#1A1A1A;-webkit-font-smoothing:antialiased}}
a{{color:#0055CC;text-decoration:none}}
/* Top nav */
.topnav{{display:flex;justify-content:space-between;align-items:center;padding:.6rem 1rem;background:#0a0a0a;font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase}}
.topnav a{{color:rgba(255,255,255,.6);text-decoration:none}}
.topnav a:hover{{color:#fff}}
/* Hero */
.hero{{background:#111;border-top:4px solid #E10600;padding:1.4rem 1.5rem 1.2rem}}
.hero-eyebrow{{font-size:10px;font-weight:700;letter-spacing:0.13em;text-transform:uppercase;color:#E10600;margin-bottom:6px}}
.hero-title{{font-size:26px;font-weight:800;color:#fff;letter-spacing:-0.025em;margin-bottom:10px;line-height:1.1}}
.hero-badges{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}}
.badge{{font-size:11px;font-weight:600;padding:3px 9px;border-radius:5px}}
.badge-sprint{{background:#FF6B00;color:#fff}}
.badge-deadline{{background:rgba(255,255,255,0.1);color:rgba(255,255,255,0.75);border:1px solid rgba(255,255,255,0.18)}}
.badge-round{{background:rgba(255,255,255,0.07);color:rgba(255,255,255,0.4)}}
.badge-overtake{{background:rgba(234,243,222,0.15);color:#8DD48A;border:1px solid rgba(141,212,138,0.3);cursor:default}}
.hero-updated{{font-size:11px;color:rgba(255,255,255,0.3)}}
/* Circuit + weather zone */
.circuit-weather{{background:#1A1A1A;padding:0 1.5rem 1.2rem;display:flex;gap:16px;align-items:center}}
.circuit-wrap{{flex:1;min-width:0;display:flex;align-items:center;justify-content:center;height:100px}}
.circuit-svg{{height:100%;max-width:100%;color:#444;display:block}}
/* Weather strip */
.wx-strip{{display:flex;gap:0;border:1px solid #2E2E2E;border-radius:8px;overflow:hidden;flex-shrink:0}}
.wx-cell{{padding:.55rem .65rem;text-align:center;border-right:1px solid #2E2E2E;display:flex;flex-direction:column;align-items:center;gap:2px;min-width:60px}}
.wx-cell:last-child{{border-right:none}}
.wx-label{{font-size:9px;font-weight:700;color:#666;text-transform:uppercase;letter-spacing:.06em;white-space:nowrap}}
.wx-date{{font-size:10px;color:#555;white-space:nowrap}}
.wx-icon{{width:22px;height:22px;color:#888;display:flex;align-items:center;justify-content:center;margin:1px 0}}
.wx-icon:empty{{display:none}}
.wx-icon svg{{width:100%;height:100%}}
.wx-temp{{font-size:13px;font-weight:600;color:#ccc;letter-spacing:-.01em}}
.wx-precip{{font-size:10px;color:#5B9BD5;font-weight:600;white-space:nowrap}}
/* Content */
.content{{max-width:680px;margin:0 auto;padding:1.35rem 1.25rem 2.5rem}}
/* Sections */
.section{{margin-bottom:1.75rem}}
.section-header{{display:flex;align-items:center;gap:10px;margin-bottom:1rem}}
.section-bar{{width:4px;height:20px;background:#E10600;border-radius:2px;flex-shrink:0}}
.section-title{{font-size:15px;font-weight:700;color:#1A1A1A;letter-spacing:-.01em}}
.section-sub{{font-size:12px;color:#888;font-weight:400;margin-left:2px}}
/* Callout */
.callout{{background:#FFF8ED;border:1.5px solid #F5A623;border-radius:10px;padding:.9rem 1.1rem;margin-bottom:1.75rem}}
.callout-header{{display:flex;align-items:center;gap:7px;margin-bottom:5px}}
.callout-icon{{width:20px;height:20px;border-radius:50%;background:#F5A623;color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;flex-shrink:0;line-height:1}}
.callout-label{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#B85C00}}
.callout-text{{font-size:13.5px;color:#3D2B00;line-height:1.55}}
/* Budget table */
.table-wrap{{background:#fff;border:1px solid #E4E4E4;border-radius:10px;overflow:hidden}}
.budget-table{{width:100%;border-collapse:collapse;font-size:13px}}
.budget-table th{{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:#999;text-align:left;padding:10px 12px 8px;border-bottom:1px solid #EBEBEB;background:#FAFAFA}}
.budget-table td{{padding:9px 12px;border-bottom:1px solid #F2F2F2;color:#1A1A1A;vertical-align:top;line-height:1.45}}
.budget-table tr:last-child td{{border-bottom:none}}
.budget-val{{font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}}
.highlight-row td{{background:#EEF5FF}}
.highlight-row .budget-val{{color:#0059CC}}
.optimal-badge{{display:inline-block;font-size:10px;font-weight:700;background:#0059CC;color:#fff;padding:2px 7px;border-radius:4px;margin-left:7px;vertical-align:middle;letter-spacing:.02em}}
/* Captains */
.captain-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.captain-card{{background:#fff;border:1px solid #E4E4E4;border-radius:12px;overflow:hidden}}
.captain-team-bar{{height:5px}}
.captain-body{{padding:.9rem 1rem}}
.captain-card-label{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#999;margin-bottom:9px}}
.captain-layout{{display:flex;gap:12px;align-items:flex-start}}
.captain-photo-wrap{{flex-shrink:0;width:52px;height:52px;border-radius:50%;overflow:hidden;border-width:2.5px;border-style:solid;background:#f5f5f5;display:flex;align-items:center;justify-content:center}}
.captain-photo-wrap .av{{width:100%;height:100%;object-fit:cover;object-position:top center}}
.captain-photo-wrap .av-fb{{width:100%;height:100%;font-size:11px}}
.captain-info{{flex:1;min-width:0}}
.captain-name{{font-size:15px;font-weight:700;color:#1A1A1A;margin-bottom:2px;letter-spacing:-.01em}}
.captain-price{{font-size:12px;color:#888;margin-bottom:6px}}
.captain-reason{{font-size:12.5px;color:#444;line-height:1.5}}
/* Avatars */
.av{{border-radius:50%;object-fit:cover;object-position:top center;display:block;flex-shrink:0}}
.av-fb{{border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:700;color:#fff;flex-shrink:0;letter-spacing:.02em}}
/* Pills */
.driver-groups{{display:flex;flex-direction:column;gap:13px}}
.driver-group{{display:flex;align-items:flex-start;gap:10px}}
.driver-group-label{{font-size:10px;font-weight:700;width:66px;flex-shrink:0;padding-top:7px;text-transform:uppercase;letter-spacing:.07em}}
.label-buy{{color:#1A7C2E}}.label-consider{{color:#9B5500}}.label-avoid{{color:#B71C1C}}
.pills{{display:flex;flex-wrap:wrap;gap:7px}}
.pill{{font-size:12.5px;padding:5px 11px 5px 5px;border-radius:24px;display:inline-flex;align-items:center;gap:6px;font-weight:500;line-height:1.3}}
.pill-avoid{{padding:5px 11px}}
.pill-buy{{background:#E7F6EC;color:#145C23;border:1.5px solid #82CCA0}}
.pill-consider{{background:#FFF4DE;color:#7A3D00;border:1.5px solid #FFC960}}
.pill-avoid{{background:#FFEBEB;color:#8B1A1A;border:1.5px solid #FFAAAA}}
.pill-note{{font-size:11px;opacity:.65}}
/* Chips */
.chip-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.chip-card{{background:#fff;border:1px solid #E4E4E4;border-radius:10px;padding:.85rem 1rem;border-left:4px solid var(--chip-color,#E4E4E4)}}
.chip-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}}
.chip-name-wrap{{display:flex;align-items:center;gap:7px}}
.chip-icon{{width:17px;height:17px;flex-shrink:0;color:#666;display:flex}}
.chip-icon svg{{width:100%;height:100%}}
.chip-name{{font-size:13.5px;font-weight:700;color:#1A1A1A}}
.chip-rec{{font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;letter-spacing:.03em;white-space:nowrap}}
.rec-use{{background:#E7F6EC;color:#145C23}}.rec-save{{background:#EEF5FF;color:#0044AA}}.rec-maybe{{background:#FFF4DE;color:#7A3D00}}
.chip-body{{font-size:12px;color:#555;line-height:1.5}}
/* Watch */
.watch-list{{background:#fff;border:1px solid #E4E4E4;border-radius:10px;overflow:hidden}}
.watch-item{{display:flex;gap:12px;font-size:13px;color:#333;line-height:1.55;padding:10px 14px;border-bottom:1px solid #F2F2F2}}
.watch-item:last-child{{border-bottom:none}}
.watch-num{{font-size:11px;font-weight:800;color:#E10600;flex-shrink:0;width:16px;text-align:right;margin-top:2px;font-variant-numeric:tabular-nums}}
/* Arc */
.arc-card{{background:#fff;border:1px solid #E4E4E4;border-radius:10px;padding:1rem 1.1rem;border-top:4px solid #E10600}}
.arc-text{{font-size:13px;color:#444;line-height:1.6}}
/* Sources */
.sources-list{{background:#fff;border:1px solid #E4E4E4;border-radius:10px;overflow:hidden}}
.source-item{{display:flex;align-items:baseline;gap:8px;font-size:12px;color:#555;padding:8px 14px;border-bottom:1px solid #F2F2F2}}
.source-item:last-child{{border-bottom:none}}
.source-channel{{font-weight:700;color:#1A1A1A;min-width:130px;flex-shrink:0}}
.source-link{{color:#0055CC}}
/* Mobile */
@media(max-width:560px){{
  .captain-grid{{grid-template-columns:1fr}}
  .chip-grid{{grid-template-columns:1fr}}
  .circuit-weather{{flex-direction:column;gap:10px;padding-bottom:1rem}}
  .wx-strip{{width:100%}}
  .circuit-wrap{{height:80px;width:100%}}
  .budget-table{{font-size:12px}}
  .budget-table th,.budget-table td{{padding:5px 8px}}
}}
</style>
</head>
<body>
<nav class="topnav">
  {'<a class="topnav-back" href="../../">← Latest race</a>' if is_archive else '<span></span>'}
  <a class="topnav-all" href="{'../../archive.html' if is_archive else 'archive.html'}">All races →</a>
</nav>
<div class="hero">
  <div class="hero-eyebrow">F1 Fantasy · {season}</div>
  <div class="hero-title">{race}</div>
  <div class="hero-badges">
    <span class="badge badge-round">Round {strategy.get('round','')}</span>
    {sprint_badge}{dl_badge}{overtake_badge}
  </div>
  <div class="hero-updated">Updated {updated}</div>
</div>
{circuit_weather_section}
<div class="content">
  <div class="callout">
    <div class="callout-header">
      <div class="callout-icon">?</div>
      <div class="callout-label">Central unknown</div>
    </div>
    <div class="callout-text">{strategy.get('central_unknown','')}</div>
  </div>
  <div class="section">
    <div class="section-header"><div class="section-bar"></div><div class="section-title">Meta template <span class="section-sub">{meta_name}</span></div></div>
    <div class="table-wrap"><table class="budget-table">
      <thead><tr><th>Budget</th><th>Core</th><th>B-tier fills</th></tr></thead>
      <tbody>{budget_rows()}</tbody>
    </table></div>
  </div>
  <div class="section">
    <div class="section-header"><div class="section-bar"></div><div class="section-title">×2 Captain</div></div>
    <div class="captain-grid">{captain_cards()}</div>
  </div>
  <div class="section">
    <div class="section-header"><div class="section-bar"></div><div class="section-title">B-tier drivers</div></div>
    <div class="driver-groups">
      {pill_row("label-buy","Buy",btier.get("buy",[]),"pill-buy")}
      {pill_row("label-consider","Consider",btier.get("consider",[]),"pill-consider")}
      {avoid_row()}
    </div>
  </div>
  <div class="section">
    <div class="section-header"><div class="section-bar"></div><div class="section-title">Chip strategy</div></div>
    <div class="chip-grid">{chip_cards()}</div>
  </div>
  <div class="section">
    <div class="section-header"><div class="section-bar"></div><div class="section-title">Watch before deadline</div></div>
    <div class="watch-list">{watch_items()}</div>
  </div>
  <div class="section">
    <div class="section-header"><div class="section-bar"></div><div class="section-title">{arc_title}</div></div>
    <div class="arc-card"><div class="arc-text">{arc}</div></div>
  </div>
  <div class="section">
    <div class="section-header"><div class="section-bar"></div><div class="section-title">Sources</div></div>
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
