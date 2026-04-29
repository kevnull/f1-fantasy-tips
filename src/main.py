"""
main.py — Orchestrator. Run this to generate docs/index.html.

Usage:
    python src/main.py --race Miami
    python src/main.py --race "Miami" --skip-fetch  # use cached transcripts
    python src/main.py --race "Miami" --skip-synthesize  # use cached strategy.json
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Add src/ to path when run from repo root
sys.path.insert(0, str(Path(__file__).parent))

from fetch import fetch_transcripts
from synthesize import synthesize
from render import render
from archive import save as save_archive, render_all as render_archive_all

TRANSCRIPT_DIR = "transcripts"
STRATEGY_CACHE = "data/strategy.json"
OUTPUT_PATH = "docs/index.html"


def _hash_sources(transcripts: list[dict], race: str) -> str:
    """Stable hash over (race, sorted video_ids, transcript text). Race included so
    re-running for a different GP with stale transcripts still re-synthesizes."""
    h = hashlib.sha256()
    h.update(race.lower().encode())
    for t in sorted(transcripts, key=lambda x: x["video_id"]):
        h.update(b"\0")
        h.update(t["video_id"].encode())
        h.update(b"\0")
        h.update(t["transcript_text"].encode())
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Generate F1 Fantasy tips page")
    parser.add_argument("--race", default="Miami", help="Race name e.g. Miami, Monaco, Canada")
    parser.add_argument("--skip-fetch", action="store_true", help="Reuse existing transcripts")
    parser.add_argument("--skip-synthesize", action="store_true", help="Reuse cached strategy.json")
    parser.add_argument("--render-only", action="store_true", help="Skip fetch + synthesize, just render from cached strategy.json")
    parser.add_argument("--force-synthesize", action="store_true", help="Re-synthesize even if source hash matches cache")
    args = parser.parse_args()

    print(f"\n=== F1 Fantasy Tips Generator — {args.race} GP ===\n")

    if args.render_only:
        if not Path(STRATEGY_CACHE).exists():
            print(f"[error] --render-only requires {STRATEGY_CACHE} to exist.")
            sys.exit(1)
        with open(STRATEGY_CACHE) as f:
            strategy = json.load(f)
        print(f"[render-only] Loaded {STRATEGY_CACHE}")
        render(strategy, output_path=OUTPUT_PATH)
        render_archive_all()
        print(f"\nDone. Open: {OUTPUT_PATH}")
        return

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

    # Step 2: Synthesize (skip if source hash matches cached strategy)
    source_hash = _hash_sources(transcripts, args.race)
    cached_strategy = None
    if Path(STRATEGY_CACHE).exists():
        try:
            with open(STRATEGY_CACHE) as f:
                cached_strategy = json.load(f)
        except json.JSONDecodeError:
            cached_strategy = None

    if args.skip_synthesize and cached_strategy is not None:
        print(f"[skip] Using cached strategy from {STRATEGY_CACHE}")
        strategy = cached_strategy
    elif (not args.force_synthesize
          and cached_strategy is not None
          and cached_strategy.get("_source_hash") == source_hash):
        print(f"[cache hit] Source set unchanged ({source_hash[:12]}); skipping Claude API call.")
        strategy = cached_strategy
    else:
        strategy = synthesize(transcripts, args.race)
        strategy["_source_hash"] = source_hash
        Path(STRATEGY_CACHE).parent.mkdir(parents=True, exist_ok=True)
        with open(STRATEGY_CACHE, "w") as f:
            json.dump(strategy, f, indent=2)
        print(f"Strategy saved to {STRATEGY_CACHE}")

    # Step 3: Save to archive + render current + re-render archive
    archive_path = save_archive(strategy)
    print(f"Archived to {archive_path}")
    render(strategy, output_path=OUTPUT_PATH)
    render_archive_all()
    print(f"\nDone. Open: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
