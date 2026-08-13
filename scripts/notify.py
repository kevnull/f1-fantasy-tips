"""
notify.py — Build a plain-text summary of the current strategy for ntfy email.

Usage:
    python scripts/notify.py > /tmp/f1-summary.txt
"""
import json
import sys
from pathlib import Path

STRATEGY = Path("data/strategy.json")


def _short(s: str, n: int = 240) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def build(strategy: dict) -> str:
    race = strategy.get("race", "GP")
    deadline = strategy.get("deadline") or "unknown"
    url = "https://kevnull.github.io/f1-fantasy-tips/"
    lines = [f"F1 Fantasy — {race}", f"Deadline: {deadline}", f"Full page: {url}", ""]

    caps = strategy.get("captains") or []
    if caps:
        lines.append("CAPTAINS")
        for c in caps[:3]:
            label = c.get("label", "Pick")
            name = c.get("name", "?")
            price = c.get("price", "")
            lines.append(f"• {label}: {name} ({price})")
            reason = c.get("reason")
            if reason: lines.append(f"    {_short(reason)}")
        lines.append("")

    btier = strategy.get("btier") or {}
    buys = btier.get("buy") or []
    if buys:
        lines.append("BUY / HOLD")
        for b in buys[:5]:
            name = b.get("name", "?")
            price = b.get("price", "")
            lines.append(f"• {name} ({price})")
            note = b.get("note")
            if note: lines.append(f"    {_short(note, 200)}")
        lines.append("")
    sells = btier.get("sell") or []
    if sells:
        lines.append("SELL / AVOID")
        for s in sells[:4]:
            name = s.get("name", "?")
            price = s.get("price", "")
            lines.append(f"• {name} ({price})")
            note = s.get("note")
            if note: lines.append(f"    {_short(note, 180)}")
        lines.append("")

    chips = strategy.get("chips") or []
    if chips:
        lines.append("CHIPS")
        for c in chips[:4]:
            name = c.get("name", "?")
            rec = (c.get("rec") or "").upper()
            lines.append(f"• {name}: {rec}")
            reason = c.get("reason")
            if reason: lines.append(f"    {_short(reason, 200)}")
        lines.append("")

    watch = strategy.get("watch_items") or []
    if watch:
        lines.append("WATCH")
        for w in watch[:5]:
            lines.append(f"• {_short(w, 220)}")
        lines.append("")

    arc = strategy.get("arc")
    if arc:
        lines.append("SEASON ARC")
        lines.append(_short(arc, 500))

    return "\n".join(lines)


def main():
    if not STRATEGY.exists():
        print("(no strategy.json)", file=sys.stderr)
        sys.exit(1)
    print(build(json.loads(STRATEGY.read_text())))


if __name__ == "__main__":
    main()
