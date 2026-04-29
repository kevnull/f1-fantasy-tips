# F1 Fantasy Tips — Public Site

Generates a race-week strategy page for F1 Fantasy, synthesized from YouTube transcripts. Deploys to GitHub Pages via GitHub Actions.

## How it works

1. `src/fetch.py` — finds latest race-week videos on the 5 trusted channels, downloads VTT transcripts via yt-dlp
2. `src/synthesize.py` — sends transcripts to Claude API, returns structured JSON (template, captains, B-tier, chips, watch items, arc, sources)
3. `src/render.py` — fetches OpenF1 driver data (photos, team colors), renders `docs/index.html` from the synthesis JSON
4. `src/main.py` — orchestrates the above, accepts `--race` arg

**GitHub Actions only renders + deploys** (uses `--render-only`). It does NOT fetch or synthesize, because YouTube blocks the runner IPs for transcript downloads ("Sign in to confirm you're not a bot"). Fetch + synthesize must run locally.

## Local refresh (race week)

```bash
set -a; source .env; set +a
.venv/bin/python src/main.py --race "Miami"   # fetch + synthesize + render
git add data/strategy.json docs/index.html
git commit -m "Refresh strategy: Miami GP"
git push   # triggers Pages re-render + deploy
```

## Render-only (no API calls)

```bash
.venv/bin/python src/main.py --render-only    # uses cached data/strategy.json
```

## Refresh overtake ranking (a few times per season)

```bash
.venv/bin/python src/overtakes.py refresh     # re-scrapes racingpass.net
git add data/cache/overtakes.json
git commit -m "Refresh overtake ranking"
```

The data only updates when racingpass posts new race stats. Render won't auto-fetch — if `data/cache/overtakes.json` is missing, the badge silently skips.

## Channels

| Channel | URL | Focus |
|---------|-----|-------|
| ZachGP | https://www.youtube.com/@ZachGP22/videos | Best teams, initial thoughts |
| FanAmp | https://www.youtube.com/@FanAmp/videos | Best lineups, final picks |
| ReinFantasy | https://www.youtube.com/@ReinFantasy/videos | Team selection, strategy |
| FormulaFantasyHub | https://www.youtube.com/@formulafantasyhub/videos | Rob's team selection |
| F1FantasyPolePosition | https://www.youtube.com/@f1fantasypoleposition/videos | Refresh, transfer targets, team selection |

## Transcript method

Always use yt-dlp. Do NOT use Claude in Chrome for transcripts.

```bash
yt-dlp --write-auto-sub --sub-lang en --skip-download -o "transcripts/%(id)s" VIDEO_URL
```

VTT files land in `transcripts/`. `fetch.py` parses them to plain text (deduplicates repeated caption lines).

## Pricing note

The F1 Fantasy API blocks server-side requests (TLS fingerprinting). Current prices can't be fetched programmatically. Two options:
- Prices come from synthesized transcripts (YouTubers mention them)
- Override manually in `data/prices.json` each week

## Deployment

- GitHub Pages serves from `docs/` on `main` branch
- GitHub Actions commits updated `docs/index.html` after each run
- Set `ANTHROPIC_API_KEY` in repo Settings → Secrets → Actions

## Key facts (update each season)

- Constructor standings 2026: Mercedes 1st, Ferrari 2nd, McLaren 3rd
- Sprint weekends: deadline after FP1 + sprint qualifying only
- Price mechanics: 3-race rolling average
