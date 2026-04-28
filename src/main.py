"""
main.py — Orchestrator. Run this to generate docs/index.html.

Usage:
    python src/main.py --race Miami
    python src/main.py --race "Miami" --skip-fetch  # use cached transcripts
    python src/main.py --race "Miami" --skip-synthesize  # use cached strategy.json
"""

import argparse
import json
import sys
from pathlib import Path

# Add src/ to path when run from repo root
sys.path.insert(0, str(Path(__file__).parent))

from fetch import fetch_transcripts
from synthesize import synthesize
from render import render

TRANSCRIPT_DIR = "transcripts"
STRATEGY_CACHE = "data/strategy.json"
OUTPUT_PATH = "docs/index.html"


def main():
    parser = argparse.ArgumentParser(description="Generate F1 Fantasy tips page")
    parser.add_argument("--race", default="Miami", help="Race name e.g. Miami, Monaco, Canada")
    parser.add_argument("--skip-fetch", action="store_true", help="Reuse existing transcripts")
    parser.add_argument("--skip-synthesize", action="store_true", help="Reuse cached strategy.json")
    args = parser.parse_args()

    print(f"\n=== F1 Fantasy Tips Generator — {args.race} GP ===\n")

    # Step 1: Fetch transcripts
    if args.skip_fetch and Path(TRANSCRIPT_DIR).exists():
        print(f"[skip] Using cached transcripts in {TRANSCRIPT_DIR}/")
        # Reconstruct transcript list from cached VTT files
        from fetch import parse_vtt, CHANNELS
        transcripts = []
        for vtt in sorted(Path(TRANSCRIPT_DIR).glob("*.en.vtt")):
            text = parse_vtt(str(vtt))
            transcripts.append({
                "channel": "cached",
                "video_id": vtt.stem.replace(".en", ""),
                "title": vtt.stem,
                "url": f"https://www.youtube.com/watch?v={vtt.stem.replace('.en','')}",
                "transcript_text": text,
            })
    else:
        transcripts = fetch_transcripts(args.race, output_dir=TRANSCRIPT_DIR)

    if not transcripts:
        print("[error] No transcripts fetched. Exiting.")
        sys.exit(1)

    # Step 2: Synthesize
    if args.skip_synthesize and Path(STRATEGY_CACHE).exists():
        print(f"[skip] Using cached strategy from {STRATEGY_CACHE}")
        with open(STRATEGY_CACHE) as f:
            strategy = json.load(f)
    else:
        strategy = synthesize(transcripts, args.race)
        Path(STRATEGY_CACHE).parent.mkdir(parents=True, exist_ok=True)
        with open(STRATEGY_CACHE, "w") as f:
            json.dump(strategy, f, indent=2)
        print(f"Strategy saved to {STRATEGY_CACHE}")

    # Step 3: Render
    render(strategy, output_path=OUTPUT_PATH)
    print(f"\nDone. Open: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
