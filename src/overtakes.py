"""
overtakes.py — Scrape racingpass.net circuit overtake stats and expose lookup.

Cached to data/cache/overtakes.json. Re-scrape with refresh_overtakes() (or just
delete the cache file). The data only updates when a new GP runs, so refreshing
once a week from CI is enough.
"""

import json
import re
import subprocess
from pathlib import Path

URL = "https://racingpass.net/circuits/"
CACHE = Path("data/cache/overtakes.json")

# Map a strategy/race name (lowercase) → the racingpass circuit name.
# Strategy names come in like "Miami GP", "Spain", "Netherlands" — match by substring.
RACE_TO_CIRCUIT = {
    "bahrain":         "Sakhir",          # 2026 uses standard Bahrain layout, not "Sakhir GP" outer loop
    "saudi arabia":    "Jeddah",
    "australia":       "Albert Park",
    "japan":           "Suzuka",
    "china":           "Shanghai",
    "miami":           "Miami",
    "emilia romagna":  "Imola",
    "imola":           "Imola",
    "monaco":          "Monaco",
    "spain":           "Catalunya",
    "canada":          "Montreal",
    "austria":         "Red Bull Ring",
    "great britain":   "Silverstone",
    "british":         "Silverstone",
    "hungary":         "Hungaroring",
    "belgium":         "Spa Francorchamps",
    "netherlands":     "Zandvoort",
    "italy":           "Monza",
    "azerbaijan":      "Baku",
    "singapore":       "Marina Bay",
    "united states":   "Cota",
    "mexico":          "Mexico City",
    "brazil":          "Interlagos",
    "las vegas":       "Las Vegas",
    "qatar":           "Losail",
    "abu dhabi":       "Abu Dhabi",
}


def _normalize_circuit_name(s: str) -> str:
    """Strip year-range suffixes like ' (2023-)' and trim."""
    return re.sub(r"\s*\(.+?\)\s*$", "", s).strip()


def _is_current_layout(years: str) -> bool:
    """Filter racingpass rows to current layouts only.

    Rows with a closed year range like '2007-22' or '2018-22' are obsolete.
    Rows with '<year>-' (open ended) or empty year-range are current.
    """
    y = years.strip()
    if not y: return True
    # closed range "2007-22" or "2018-22" → second part is a year (1-2 digits) → obsolete
    m = re.match(r"^\d{4}-(\d{2,4})$", y)
    if m: return False
    # comma-separated like "1991-06,2023-": current if any segment is open-ended
    return any(seg.strip().endswith("-") and not seg.strip().endswith(re.match(r"\d{4}-(\d{2,4})", seg.strip()).group(1) if re.match(r"\d{4}-(\d{2,4})", seg.strip()) else "")
               for seg in y.split(",")) or y.endswith("-")


def fetch_overtakes() -> list[dict]:
    """Scrape racingpass.net and return all rows, parsed and sorted by avg_since_2017 desc."""
    # racingpass.net is behind Cloudflare-style TLS fingerprinting; the python
    # `requests` library gets a 403 but plain `curl` succeeds.
    result = subprocess.run([
        "curl", "-sSL",
        "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: en-US,en;q=0.9",
        URL,
    ], capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")
    html = result.stdout

    m = re.search(r'<table[^>]*tablepress-id-739[^>]*>(.*?)</table>', html, re.S)
    if not m:
        raise RuntimeError("Couldn't find overtakes table on racingpass.net")
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', m.group(1), re.S)

    parsed = []
    for r in rows[1:]:
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', r, re.S)]
        if len(cells) < 5: continue
        m2 = re.match(r"^(.+?)\s*\((.+?)\)\s*$", cells[0])
        circuit = m2.group(1).strip() if m2 else cells[0]
        years   = m2.group(2) if m2 else ""
        try:
            avg = float(cells[1])
        except ValueError:
            continue
        parsed.append({"circuit": circuit, "years": years, "avg_since_2017": avg})

    parsed.sort(key=lambda x: -x["avg_since_2017"])
    return parsed


def current_calendar_ranking() -> list[dict]:
    """Filter scraped data to current 2026 calendar circuits, dedup by circuit name keeping
    the row with the most recent (open-ended) year range, then re-rank 1..N."""
    raw = _load_or_fetch()
    current_names = set(RACE_TO_CIRCUIT.values())

    # Group by circuit, keep current-layout row (or first if none flagged)
    by_circuit: dict[str, dict] = {}
    for row in raw:
        if row["circuit"] not in current_names: continue
        prev = by_circuit.get(row["circuit"])
        if prev is None or _is_current_layout(row["years"]):
            by_circuit[row["circuit"]] = row

    ranked = sorted(by_circuit.values(), key=lambda x: -x["avg_since_2017"])
    for i, row in enumerate(ranked, 1):
        row["rank"] = i
        row["total"] = len(ranked)
    return ranked


def _load_or_fetch() -> list[dict]:
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    print(f"  [overtakes] Fetching racingpass.net (no cache at {CACHE})")
    data = fetch_overtakes()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=2))
    return data


def refresh() -> list[dict]:
    """Force refresh from racingpass.net and update the cache."""
    print(f"  [overtakes] Refreshing from {URL}")
    data = fetch_overtakes()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=2))
    return data


def lookup_rank(race_name: str) -> dict | None:
    """Returns {rank, total, avg, circuit} for the given race name (e.g. 'Miami GP'),
    or None if the race isn't mappable."""
    rl = race_name.lower()
    circuit_name = None
    for race_key, circuit in RACE_TO_CIRCUIT.items():
        if race_key in rl:
            circuit_name = circuit
            break
    if not circuit_name: return None
    ranking = current_calendar_ranking()
    for row in ranking:
        if row["circuit"] == circuit_name:
            return {"rank": row["rank"], "total": row["total"],
                    "avg": row["avg_since_2017"], "circuit": row["circuit"]}
    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        refresh()
    for row in current_calendar_ranking():
        print(f"  {row['rank']:2d}/{row['total']}  {row['circuit']:25s} {row['avg_since_2017']:5.1f}")
