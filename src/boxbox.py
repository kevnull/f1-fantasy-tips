"""
boxbox.py — Fetch BoxBoxF1Fantasy's ML-based predictions and format them as a
transcript-shaped source for the synth pipeline.

They publish structured data at:
  https://boxboxf1fantasy.com/data/ai-summary.json      (compact)
  https://boxboxf1fantasy.com/data/predictions.json     (full)

robots.txt explicitly welcomes AI crawlers; llms.txt documents these endpoints.
"""
import json
import urllib.request

AI_SUMMARY_URL = "https://boxboxf1fantasy.com/data/ai-summary.json"
PREDICTIONS_URL = "https://boxboxf1fantasy.com/data/predictions.json"
UA = "f1-fantasy-tips/1.0 (kc@kevnull.com)"


def _get_json(url: str, timeout: int = 15) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception as e:
        print(f"  [boxbox] fetch failed {url}: {e}")
        return None


def _fmt_driver(d: dict) -> str:
    ci = d.get("confidence_interval_90") or {}
    return (
        f"  #{d.get('rank','?')} {d.get('name','?')} ({d.get('id','?')}) — "
        f"exp {d.get('expected_points','?')} pts, proj {d.get('projected_points','?')} pts, "
        f"price {d.get('current_price_m','?')}M, ppm {d.get('points_per_million','?')}, "
        f"value {d.get('value_score','?')}, risk {d.get('risk','?')}, "
        f"DNF {d.get('dnf_probability','?')}, "
        f"pred quali P{d.get('predicted_quali','?')} → finish P{d.get('predicted_finish','?')}, "
        f"90% CI [{ci.get('low','?')}, {ci.get('high','?')}]"
    )


def _fmt_constructor(c: dict) -> str:
    ci = c.get("confidence_interval_90") or {}
    return (
        f"  #{c.get('rank','?')} {c.get('name','?')} ({c.get('id','?')}) — "
        f"exp {c.get('expected_points','?')} pts, proj {c.get('projected_points','?')} pts, "
        f"price {c.get('current_price_m','?')}M, ppm {c.get('points_per_million','?')}, "
        f"value {c.get('value_score','?')}, risk {c.get('risk','?')}, "
        f"90% CI [{ci.get('low','?')}, {ci.get('high','?')}]"
    )


def fetch_boxbox_source(race_name: str) -> dict | None:
    """Return a transcript-shaped dict with BoxBox ML predictions, or None on failure.
    race_name arg is currently just for logging — endpoint always returns the current round."""
    summary = _get_json(AI_SUMMARY_URL)
    if not summary:
        return None

    race = summary.get("race", "?")
    round_ = summary.get("round", "?")
    circuit = summary.get("circuit", "?")
    sprint = summary.get("is_sprint_weekend", False)
    plain = summary.get("plain_english_summary", "")
    gen_at = summary.get("source_predictions_generated_at", "")

    lines = [
        f"BoxBoxF1Fantasy — ML predictions for {race} (Round {round_}, {circuit})",
        f"Sprint weekend: {sprint}. Predictions generated: {gen_at}",
        f"Site summary: {plain}",
        "",
    ]

    boost = summary.get("recommended_boost_driver")
    if boost:
        lines += ["ML-RECOMMENDED CAPTAIN (2x):", _fmt_driver(boost), ""]

    top_d = summary.get("top_drivers") or []
    if top_d:
        lines.append(f"TOP {len(top_d)} DRIVERS (by expected points):")
        lines += [_fmt_driver(d) for d in top_d]
        lines.append("")

    top_c = summary.get("top_constructors") or []
    if top_c:
        lines.append(f"TOP {len(top_c)} CONSTRUCTORS:")
        lines += [_fmt_constructor(c) for c in top_c]
        lines.append("")

    value_d = summary.get("value_picks_drivers") or []
    if value_d:
        lines.append("VALUE-PICK DRIVERS (best points-per-million):")
        lines += [_fmt_driver(d) for d in value_d]
        lines.append("")

    risky = summary.get("high_risk_drivers") or summary.get("dnf_risk_drivers") or []
    if risky:
        lines.append("HIGH DNF-RISK DRIVERS:")
        lines += [_fmt_driver(d) for d in risky]
        lines.append("")

    print(f"[BoxBoxF1Fantasy-ML] → summary for {race} ({len(top_d)} drivers, {len(top_c)} constructors)")

    return {
        "channel": "BoxBoxF1Fantasy-ML",
        "video_id": f"boxbox-ml-{summary.get('season','')}-{round_}",
        "title": f"BoxBoxF1Fantasy ML predictions — {race}",
        "url": summary.get("canonical_pages", {}).get("race_picks", AI_SUMMARY_URL),
        "transcript_text": "\n".join(lines),
    }


if __name__ == "__main__":
    src = fetch_boxbox_source("test")
    if src:
        print(src["transcript_text"])
