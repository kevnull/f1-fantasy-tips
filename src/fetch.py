"""
fetch.py — Find and download race-week YouTube transcripts via yt-dlp.

Usage:
    from fetch import fetch_transcripts
    transcripts = fetch_transcripts(race_name="Miami", output_dir="transcripts")
"""

import os
import re
import subprocess
import json
from pathlib import Path
from datetime import datetime, timedelta

CHANNELS = [
    {"name": "ZachGP",               "url": "https://www.youtube.com/@ZachGP22/videos"},
    {"name": "FanAmp",               "url": "https://www.youtube.com/@FanAmp/videos"},
    {"name": "ReinFantasy",          "url": "https://www.youtube.com/@ReinFantasy/videos"},
    {"name": "FormulaFantasyHub",    "url": "https://www.youtube.com/@formulafantasyhub/videos"},
    {"name": "F1FantasyPolePosition","url": "https://www.youtube.com/@f1fantasypoleposition/videos"},
]

YTDLP = os.environ.get("YTDLP_PATH", "yt-dlp")


def list_recent_videos(channel_url: str, max_results: int = 15) -> list[dict]:
    """Return a list of {id, title} for the most recent videos on a channel."""
    result = subprocess.run(
        [YTDLP, "--flat-playlist", "--print", "%(id)s\t%(title)s", "--no-warnings",
         "--playlist-end", str(max_results), channel_url],
        capture_output=True, text=True, timeout=60
    )
    videos = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            videos.append({"id": parts[0], "title": parts[1]})
    return videos


def score_video(title: str, race_name: str) -> int:
    """Score a video title for relevance to the current race. Higher = more relevant."""
    title_lower = title.lower()
    race_lower = race_name.lower()
    score = 0
    if race_lower in title_lower:
        score += 10
    if any(w in title_lower for w in ["team selection", "final thoughts", "best team", "transfer"]):
        score += 5
    if any(w in title_lower for w in ["2026", "f1 fantasy", "fantasy f1"]):
        score += 3
    if any(w in title_lower for w in ["tips", "picks", "lineup", "advice", "refresh"]):
        score += 2
    return score


def download_transcript(video_id: str, output_dir: str) -> str | None:
    """Download auto-generated English transcript for a video. Returns path to VTT file."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    vtt_file = out_path / f"{video_id}.en.vtt"

    if vtt_file.exists():
        print(f"  [cache] {video_id}")
        return str(vtt_file)

    result = subprocess.run(
        [YTDLP, "--write-auto-sub", "--sub-lang", "en", "--skip-download",
         "--no-warnings", "-o", str(out_path / "%(id)s"), f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True, timeout=120
    )

    if vtt_file.exists():
        return str(vtt_file)

    print(f"  [warn] No transcript for {video_id}: {result.stderr[:200]}")
    return None


def parse_vtt(filepath: str) -> str:
    """Parse a VTT file to clean deduplicated plain text."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    text_lines = []
    seen = set()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        if re.match(r"^[\d:.,\s]+-->", line) or re.match(r"^\d+$", line):
            continue
        # Strip VTT tags like <00:01:23.456><c>text</c>
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line and line not in seen:
            seen.add(line)
            text_lines.append(line)

    return " ".join(text_lines)


def fetch_transcripts(race_name: str, output_dir: str = "transcripts") -> list[dict]:
    """
    For each channel, find the best race-week video and download its transcript.

    Returns a list of:
        {channel, video_id, title, url, transcript_text}
    """
    results = []

    for channel in CHANNELS:
        print(f"\n[{channel['name']}] Listing videos...")
        try:
            videos = list_recent_videos(channel["url"])
        except Exception as e:
            print(f"  [error] {e}")
            continue

        if not videos:
            print("  [warn] No videos found")
            continue

        # Score and pick best match; for F1FantasyPolePosition grab top 3 (they post multiple per race)
        scored = sorted(videos, key=lambda v: score_video(v["title"], race_name), reverse=True)
        top_n = 3 if channel["name"] == "F1FantasyPolePosition" else 1
        picks = [v for v in scored if score_video(v["title"], race_name) > 0][:top_n]

        # Fall back to most recent if no race-specific match
        if not picks:
            picks = scored[:1]
            print(f"  [warn] No race-specific video found, using most recent: {picks[0]['title']}")

        for video in picks:
            print(f"  → {video['title']} ({video['id']})")
            vtt_path = download_transcript(video["id"], output_dir)
            if not vtt_path:
                continue
            text = parse_vtt(vtt_path)
            results.append({
                "channel": channel["name"],
                "video_id": video["id"],
                "title": video["title"],
                "url": f"https://www.youtube.com/watch?v={video['id']}",
                "transcript_text": text,
            })

    print(f"\nFetched {len(results)} transcripts.")
    return results


if __name__ == "__main__":
    import sys
    race = sys.argv[1] if len(sys.argv) > 1 else "Miami"
    results = fetch_transcripts(race)
    for r in results:
        print(f"\n{'='*60}")
        print(f"{r['channel']} — {r['title']}")
        print(r["transcript_text"][:500])
