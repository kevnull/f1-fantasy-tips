"""
synthesize.py — Send transcripts to Claude API and extract structured strategy JSON.
"""

import json
import os
import anthropic

MODEL = "claude-opus-4-6"

SYSTEM_PROMPT = """You are an F1 Fantasy analyst. You will receive transcripts from multiple YouTube
channels that cover F1 Fantasy strategy for a specific race weekend. Extract and synthesize the
actionable strategy information into structured JSON.

Be specific and concrete — include actual driver names, prices, and reasoning. Where channels
agree, state consensus. Where they diverge, note the most credible view and flag the disagreement.

Return ONLY valid JSON matching the schema below, no other text.

Schema:
{
  "race": "string — race name e.g. Miami GP",
  "round": number,
  "season": number,
  "sprint": boolean,
  "deadline": "string — e.g. May 2",
  "central_unknown": "string — 1-2 sentences on the key uncertainty this week",
  "meta_template": {
    "name": "string — e.g. Antonelli x2 + Mercedes + Ferrari",
    "budget_tiers": [
      {
        "budget": "string — e.g. 107.7M",
        "core": "string",
        "fills": "string",
        "optimal": boolean
      }
    ]
  },
  "captains": [
    {
      "label": "Primary | Differential",
      "name": "string — full name",
      "acronym": "string — 3-letter e.g. ANT",
      "price": "string — e.g. ~16.5M",
      "team": "string",
      "team_colour": "string — hex without #, from OpenF1",
      "reason": "string"
    }
  ],
  "btier": {
    "buy": [
      {"name": "string", "acronym": "string", "price": "string", "team_colour": "string", "note": "string"}
    ],
    "consider": [
      {"name": "string", "acronym": "string", "price": "string", "team_colour": "string", "note": "string"}
    ],
    "avoid": ["string"]
  },
  "chips": [
    {
      "name": "string — e.g. Wildcard",
      "rec": "use | save | maybe",
      "reason": "string"
    }
  ],
  "watch_items": ["string"],
  "arc": "string — 1 paragraph on how this race sets up the next 1-2",
  "sources": [
    {"channel": "string", "title": "string", "url": "string"}
  ]
}"""


def synthesize(transcripts: list[dict], race_name: str) -> dict:
    """
    Call Claude API with transcript content and return parsed strategy JSON.

    Args:
        transcripts: list of {channel, title, url, transcript_text}
        race_name: e.g. "Miami"

    Returns:
        Parsed strategy dict
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Build the transcript block
    transcript_block = ""
    for t in transcripts:
        transcript_block += f"\n\n--- {t['channel']}: {t['title']} ---\n"
        transcript_block += f"URL: {t['url']}\n"
        # Truncate very long transcripts to stay within context
        text = t["transcript_text"]
        if len(text) > 8000:
            text = text[:8000] + "... [truncated]"
        transcript_block += text

    user_message = f"""Race: {race_name} GP

Transcripts:
{transcript_block}

Extract the F1 Fantasy strategy for {race_name} from these transcripts and return the structured JSON."""

    print(f"Calling Claude API ({MODEL})...")
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\n\nRaw:\n{raw[:500]}")


# re import needed for code fence stripping
import re


if __name__ == "__main__":
    import sys
    from fetch import fetch_transcripts

    race = sys.argv[1] if len(sys.argv) > 1 else "Miami"
    transcripts = fetch_transcripts(race)
    result = synthesize(transcripts, race)
    print(json.dumps(result, indent=2))
