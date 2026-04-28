"""
render.py — Generate docs/index.html from strategy JSON + OpenF1 driver photos.
"""

import json
import base64
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


OPENF1_DRIVERS_URL = "https://api.openf1.org/v1/drivers?session_key=latest"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.formula1.com/",
}


def fetch_driver_photos(acronyms: list[str]) -> dict[str, str]:
    """
    Fetch headshot images from F1 CDN for the given driver acronyms.
    Returns dict of acronym → data URI (base64 PNG).
    Falls back to empty string on failure.
    """
    print("Fetching OpenF1 driver data...")
    req = urllib.request.Request(OPENF1_DRIVERS_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        drivers = json.load(r)

    # Build lookup: acronym → headshot_url + team_colour
    driver_map = {d["name_acronym"]: d for d in drivers}

    photos = {}
    for acr in acronyms:
        driver = driver_map.get(acr)
        if not driver or not driver.get("headshot_url"):
            photos[acr] = ""
            continue
        url = driver["headshot_url"]
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
                ct = r.headers.get("Content-Type", "image/png").split(";")[0].strip()
                photos[acr] = f"data:{ct};base64,{base64.b64encode(data).decode()}"
            print(f"  {acr}: {len(data)}B")
        except Exception as e:
            print(f"  {acr}: failed — {e}")
            photos[acr] = ""

    return photos


def chip_rec_class(rec: str) -> str:
    return {"use": "rec-use", "save": "rec-save", "maybe": "rec-maybe"}.get(rec.lower(), "rec-save")


def driver_photo_html(acronym: str, team_colour: str, photo_uri: str, size: int = 22) -> str:
    """Render a circular driver photo, or a team-colored initials circle as fallback."""
    colour = team_colour.lstrip("#") if team_colour else "888888"
    if photo_uri:
        return (
            f'<img class="d-avatar" style="width:{size}px;height:{size}px" '
            f'src="{photo_uri}" alt="{acronym}" '
            f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">'
            f'<span class="d-avatar-fb" style="width:{size}px;height:{size}px;background:#{colour};display:none">'
            f'{acronym}</span>'
        )
    else:
        return (
            f'<span class="d-avatar-fb" style="width:{size}px;height:{size}px;background:#{colour}">'
            f'{acronym}</span>'
        )


def render(strategy: dict, output_path: str = "docs/index.html") -> None:
    """Generate the HTML page from strategy JSON and write to output_path."""

    # Collect all acronyms we need photos for
    captain_acrs = [c["acronym"] for c in strategy.get("captains", [])]
    buy_acrs = [d["acronym"] for d in strategy.get("btier", {}).get("buy", [])]
    consider_acrs = [d["acronym"] for d in strategy.get("btier", {}).get("consider", [])]
    all_acrs = list(dict.fromkeys(captain_acrs + buy_acrs + consider_acrs))

    photos = fetch_driver_photos(all_acrs)

    # Build colour lookup from strategy data
    def colour_for(acr: str, tier_list: list) -> str:
        for d in tier_list:
            if d.get("acronym") == acr:
                return d.get("team_colour", "888888")
        return "888888"

    race = strategy.get("race", "F1 Fantasy")
    round_num = strategy.get("round", "")
    sprint = strategy.get("sprint", False)
    deadline = strategy.get("deadline", "")
    updated = datetime.now(timezone.utc).strftime("%-d %b %Y")

    # Captain cards
    captain_html = ""
    for i, cap in enumerate(strategy.get("captains", [])):
        acr = cap.get("acronym", "")
        colour = cap.get("team_colour", "888888").lstrip("#")
        photo = photos.get(acr, "")
        primary = i == 0
        border_style = "border:1.5px solid #B5D4F4" if primary else "border:0.5px solid var(--color-border-tertiary)"
        photo_html = driver_photo_html(acr, colour, photo, size=56)
        captain_html += f"""
        <div class="captain-card" style="{border_style}">
          <div class="captain-card-label">{cap.get('label','')}</div>
          <div class="captain-layout">
            <div class="captain-photo-wrap" style="border-color:#{colour}">
              {photo_html}
            </div>
            <div class="captain-info">
              <div class="captain-name">{cap.get('name','')}</div>
              <div class="captain-price">{cap.get('price','')} · {cap.get('team','')}</div>
              <div class="captain-reason">{cap.get('reason','')}</div>
            </div>
          </div>
        </div>"""

    # B-tier pills
    def pill_row(label_class: str, label: str, drivers: list, pill_class: str) -> str:
        pills = ""
        for d in drivers:
            acr = d.get("acronym", "")
            colour = d.get("team_colour", "888888")
            photo = photos.get(acr, "")
            photo_el = driver_photo_html(acr, colour, photo, size=22)
            note = f' <span class="pill-note">{d["note"]}</span>' if d.get("note") else ""
            pills += f'<span class="pill {pill_class}">{photo_el}{d.get("name",acr)} {d.get("price","")}{note}</span>'
        return f"""
        <div class="driver-group">
          <div class="driver-group-label {label_class}">{label}</div>
          <div class="pills">{pills}</div>
        </div>"""

    def avoid_pills(avoids: list) -> str:
        pills = "".join(f'<span class="pill pill-avoid">{name}</span>' for name in avoids)
        return f"""
        <div class="driver-group">
          <div class="driver-group-label label-avoid">Avoid</div>
          <div class="pills">{pills}</div>
        </div>"""

    btier = strategy.get("btier", {})
    btier_html = (
        pill_row("label-buy", "Buy", btier.get("buy", []), "pill-buy") +
        pill_row("label-consider", "Consider", btier.get("consider", []), "pill-consider") +
        avoid_pills(btier.get("avoid", []))
    )

    # Chip cards
    chip_html = ""
    for chip in strategy.get("chips", []):
        rec = chip.get("rec", "save")
        rec_label = rec.capitalize() if rec != "maybe" else "Wait"
        chip_html += f"""
        <div class="chip-card">
          <div class="chip-header">
            <span class="chip-name">{chip.get('name','')}</span>
            <span class="chip-rec {chip_rec_class(rec)}">{rec_label}</span>
          </div>
          <div class="chip-body">{chip.get('reason','')}</div>
        </div>"""

    # Watch items
    watch_html = "".join(
        f'<div class="watch-item"><div class="watch-dot"></div><div>{item}</div></div>'
        for item in strategy.get("watch_items", [])
    )

    # Sources
    source_html = ""
    for s in strategy.get("sources", []):
        source_html += f"""
        <div class="source-item">
          <span class="source-channel">{s.get('channel','')}</span>
          <a class="source-link" href="{s.get('url','#')}" target="_blank">{s.get('title','')}</a>
        </div>"""

    sprint_badge = '<span class="badge badge-sprint">Sprint weekend</span>' if sprint else ""
    deadline_badge = f'<span class="badge badge-deadline">Deadline: {deadline}</span>' if deadline else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>F1 Fantasy — {race} {strategy.get('season','')}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Helvetica,Arial,sans-serif;background:#fff;color:#111;padding:1.25rem;-webkit-font-smoothing:antialiased;line-height:1.4}}
@media(prefers-color-scheme:dark){{body{{background:#111;color:#f0f0f0}}}}
.page{{max-width:680px;margin:0 auto;padding:0.5rem 0}}
a{{color:#185FA5}}

/* Header */
.header{{display:flex;align-items:flex-start;justify-content:space-between;padding-bottom:1rem;border-bottom:0.5px solid #e0e0e0;margin-bottom:1.25rem}}
@media(prefers-color-scheme:dark){{.header{{border-color:#333}}}}
.race-title{{font-size:22px;font-weight:500;letter-spacing:-0.02em}}
.race-meta{{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}}
.badge{{font-size:11px;font-weight:500;padding:3px 8px;border-radius:6px;border:0.5px solid}}
.badge-sprint{{background:#FAEEDA;color:#633806;border-color:#FAC775}}
.badge-deadline{{background:#E6F1FB;color:#0C447C;border-color:#B5D4F4}}
.badge-round{{background:#f5f5f5;color:#555;border-color:#ddd}}
@media(prefers-color-scheme:dark){{.badge-round{{background:#222;color:#aaa;border-color:#444}}}}
.updated{{font-size:12px;color:#888;text-align:right;white-space:nowrap;padding-top:3px}}

/* Callout */
.callout{{background:#fafafa;border-left:3px solid #EF9F27;border-radius:0 6px 6px 0;padding:.75rem 1rem;margin-bottom:1.25rem}}
@media(prefers-color-scheme:dark){{.callout{{background:#1a1a1a}}}}
.callout-label{{font-size:11px;font-weight:600;color:#633806;letter-spacing:.05em;text-transform:uppercase;margin-bottom:4px}}
.callout-text{{font-size:13.5px;line-height:1.55}}

/* Sections */
.section{{margin-bottom:1.5rem}}
.section-title{{font-size:11px;font-weight:600;color:#777;letter-spacing:.07em;text-transform:uppercase;margin-bottom:.75rem;padding-bottom:.4rem;border-bottom:0.5px solid #e0e0e0}}
@media(prefers-color-scheme:dark){{.section-title{{color:#888;border-color:#333}}}}

/* Budget table */
.budget-table{{width:100%;font-size:13px;border-collapse:collapse}}
.budget-table th{{font-weight:500;color:#777;text-align:left;padding:6px 8px;border-bottom:0.5px solid #e0e0e0;font-size:12px}}
.budget-table td{{padding:7px 8px;border-bottom:0.5px solid #e0e0e0;vertical-align:top;line-height:1.4}}
.budget-table tr:last-child td{{border-bottom:none}}
@media(prefers-color-scheme:dark){{.budget-table th,.budget-table td{{border-color:#333}}}}
.budget-val{{font-weight:600;font-size:13.5px;white-space:nowrap}}
.highlight-row td{{background:rgba(100,160,255,.07)}}
.optimal-badge{{font-size:10px;background:#E6F1FB;color:#0C447C;padding:2px 6px;border-radius:4px;margin-left:6px;font-weight:600;vertical-align:middle}}

/* Captain cards */
.captain-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.captain-card{{background:#fff;border-radius:10px;padding:1rem 1.1rem;display:flex;flex-direction:column;gap:10px}}
@media(prefers-color-scheme:dark){{.captain-card{{background:#1a1a1a}}}}
.captain-card-label{{font-size:10px;font-weight:600;color:#999;text-transform:uppercase;letter-spacing:.07em}}
.captain-layout{{display:flex;gap:12px;align-items:flex-start}}
.captain-photo-wrap{{flex-shrink:0;width:56px;height:56px;border-radius:50%;overflow:hidden;border-width:2.5px;border-style:solid;background:#f5f5f5}}
.captain-photo-wrap img,.captain-photo-wrap .d-avatar{{width:100%;height:100%;object-fit:cover;object-position:top center;display:block}}
.captain-info{{flex:1;min-width:0}}
.captain-name{{font-size:16px;font-weight:600;margin-bottom:2px;letter-spacing:-0.01em}}
.captain-price{{font-size:12px;color:#888;margin-bottom:6px}}
.captain-reason{{font-size:12.5px;line-height:1.5}}

/* Driver avatar */
.d-avatar{{border-radius:50%;object-fit:cover;object-position:top center;display:block;flex-shrink:0}}
.d-avatar-fb{{border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:700;color:#fff;flex-shrink:0;letter-spacing:.02em}}

/* B-tier */
.driver-groups{{display:flex;flex-direction:column;gap:10px}}
.driver-group{{display:flex;align-items:flex-start;gap:10px}}
.driver-group-label{{font-size:10px;font-weight:600;width:58px;flex-shrink:0;padding-top:6px;text-transform:uppercase;letter-spacing:.06em}}
.label-buy{{color:#3B6D11}}.label-consider{{color:#633806}}.label-avoid{{color:#A32D2D}}
.pills{{display:flex;flex-wrap:wrap;gap:6px}}
.pill{{font-size:12.5px;padding:5px 10px 5px 5px;border-radius:20px;border:0.5px solid;line-height:1.35;display:inline-flex;align-items:center;gap:6px}}
.pill-avoid{{padding:5px 10px}}
.pill-buy{{background:#EAF3DE;color:#27500A;border-color:#C0DD97}}
.pill-consider{{background:#FAEEDA;color:#633806;border-color:#FAC775}}
.pill-avoid{{background:#FCEBEB;color:#791F1F;border-color:#F7C1C1}}
.pill-note{{font-size:11px;opacity:.7}}

/* Chips */
.chip-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.chip-card{{background:#fff;border:0.5px solid #e0e0e0;border-radius:10px;padding:.85rem 1rem}}
@media(prefers-color-scheme:dark){{.chip-card{{background:#1a1a1a;border-color:#333}}}}
.chip-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:5px}}
.chip-name{{font-size:13.5px;font-weight:600}}
.chip-rec{{font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;letter-spacing:.03em}}
.rec-use{{background:#EAF3DE;color:#27500A}}.rec-save{{background:#E6F1FB;color:#0C447C}}.rec-maybe{{background:#FAEEDA;color:#633806}}
.chip-body{{font-size:12px;color:#666;line-height:1.5}}
@media(prefers-color-scheme:dark){{.chip-body{{color:#aaa}}}}

/* Watch list */
.watch-list{{display:flex;flex-direction:column}}
.watch-item{{display:flex;gap:10px;font-size:13px;line-height:1.55;padding:8px 0;border-bottom:0.5px solid #e0e0e0}}
.watch-item:last-child{{border-bottom:none}}
@media(prefers-color-scheme:dark){{.watch-item{{border-color:#333}}}}
.watch-dot{{width:6px;height:6px;border-radius:50%;background:#EF9F27;flex-shrink:0;margin-top:7px}}

/* Arc */
.arc-text{{font-size:13px;line-height:1.6;background:#fafafa;border-radius:10px;padding:.9rem 1rem}}
@media(prefers-color-scheme:dark){{.arc-text{{background:#1a1a1a}}}}

/* Sources */
.sources-list{{display:flex;flex-direction:column}}
.source-item{{display:flex;align-items:baseline;gap:8px;font-size:12px;color:#888;padding:4px 0;border-bottom:0.5px solid #e0e0e0}}
.source-item:last-child{{border-bottom:none}}
@media(prefers-color-scheme:dark){{.source-item{{border-color:#333}}}}
.source-channel{{font-weight:600;color:#111;min-width:130px;flex-shrink:0}}
@media(prefers-color-scheme:dark){{.source-channel{{color:#f0f0f0}}}}
</style>
</head>
<body>
<div class="page">

  <div class="header">
    <div>
      <div class="race-title">{race} {strategy.get('season','')}</div>
      <div class="race-meta">
        <span class="badge badge-round">Round {round_num}</span>
        {sprint_badge}
        {deadline_badge}
      </div>
    </div>
    <div class="updated">Updated {updated}</div>
  </div>

  <div class="callout">
    <div class="callout-label">Central unknown</div>
    <div class="callout-text">{strategy.get('central_unknown','')}</div>
  </div>

  <div class="section">
    <div class="section-title">Meta template — {strategy.get('meta_template',{}).get('name','')}</div>
    <table class="budget-table">
      <thead><tr><th>Budget</th><th>Core</th><th>B-tier fills</th></tr></thead>
      <tbody>
        {''.join(
            f"<tr{' class=highlight-row' if t.get('optimal') else ''}>"
            f"<td class=\"budget-val\">{t['budget']}{'<span class=optimal-badge>optimal</span>' if t.get('optimal') else ''}</td>"
            f'<td>{t["core"]}</td><td>{t["fills"]}</td></tr>'
            for t in strategy.get('meta_template',{}).get('budget_tiers',[])
        )}
      </tbody>
    </table>
  </div>

  <div class="section">
    <div class="section-title">×2 Captain</div>
    <div class="captain-grid">{captain_html}</div>
  </div>

  <div class="section">
    <div class="section-title">B-tier drivers</div>
    <div class="driver-groups">{btier_html}</div>
  </div>

  <div class="section">
    <div class="section-title">Chip strategy</div>
    <div class="chip-grid">{chip_html}</div>
  </div>

  <div class="section">
    <div class="section-title">Watch before deadline</div>
    <div class="watch-list">{watch_html}</div>
  </div>

  <div class="section">
    <div class="section-title">{strategy.get('arc','').split('—')[0].strip() if '—' in strategy.get('arc','') else 'Race arc'}</div>
    <div class="arc-text">{strategy.get('arc','')}</div>
  </div>

  <div class="section">
    <div class="section-title">Sources</div>
    <div class="sources-list">{source_html}</div>
  </div>

</div>
</body>
</html>"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Written: {output_path} ({len(html):,} chars)")


if __name__ == "__main__":
    import sys
    strategy_file = sys.argv[1] if len(sys.argv) > 1 else "data/strategy.json"
    with open(strategy_file) as f:
        strategy = json.load(f)
    render(strategy)
