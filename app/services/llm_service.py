"""
LLM service layer for timeline event extraction.

Uses Groq (free tier) with Llama 3 for real event extraction.
Falls back to mock when GROQ_API_KEY is not set.
"""

import json
import logging
import re
from typing import List

from app.config import get_settings
from app.models.timeline import Event

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Extract timeline events from this legal document text.
Return ONLY a JSON array. Each event must have:
- "date": ISO date string (YYYY-MM-DD), use "unknown" if not found
- "description": brief description of the event
- "involved_parties": list of party names (strings)
- "significance": why this event matters (can be empty string)

Example: [{"date":"2023-06-15","description":"Contract signed","involved_parties":["Acme Corp","Beta Inc"],"significance":"Effective date"}]
Return [] if no events found.

Document text:
"""


def _parse_events_from_response(raw: str) -> List[Event]:
    """Parse LLM response into Event list. Handles markdown code blocks and malformed JSON."""
    text = raw.strip()
    # Strip markdown code block if present
    if "```json" in text:
        text = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        text = text.group(1).strip() if text else text
    elif "```" in text:
        text = re.sub(r"```\w*\s*", "", text).strip()
        text = re.sub(r"```\s*$", "", text).strip()
    try:
        data = json.loads(text)
        if not isinstance(data, list):
            return []
        events = []
        for item in data:
            if not isinstance(item, dict):
                continue
            date_val = item.get("date") or "unknown"
            desc = item.get("description") or ""
            parties = item.get("involved_parties")
            if not isinstance(parties, list):
                parties = []
            sig = item.get("significance") or ""
            events.append(
                Event(
                    date=str(date_val),
                    description=str(desc),
                    involved_parties=[str(p) for p in parties],
                    significance=str(sig),
                )
            )
        return events
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Failed to parse LLM response as JSON: %s", e)
        return []


def _mock_events(text_chunk: str) -> List[Event]:
    """Fallback: return placeholder events when LLM is unavailable."""
    logger.debug("Mock LLM processing chunk length=%d", len(text_chunk))
    return [
        Event(
            date="2023-01-15",
            description="Sample event extracted from document (mock).",
            involved_parties=["Party A", "Party B"],
            significance="Mock significance for testing.",
        ),
    ]


class LLMService:
    """
    Encapsulates all LLM calls. Uses Groq (free) when GROQ_API_KEY is set,
    otherwise falls back to mock events.
    """

    async def extract_events_from_chunk(self, text_chunk: str) -> List[Event]:
        """Extract timeline events from a single text chunk using Groq Llama 3."""
        settings = get_settings()
        api_key = (settings.groq_api_key or "").strip()

        if not api_key:
            logger.debug("GROQ_API_KEY not set; using mock events")
            return _mock_events(text_chunk)

        try:
            from groq import AsyncGroq

            client = AsyncGroq(api_key=api_key)
            prompt = EXTRACTION_PROMPT + (text_chunk[:32000] if len(text_chunk) > 32000 else text_chunk)
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2048,
            )
            content = response.choices[0].message.content or ""
            events = _parse_events_from_response(content)
            logger.info("Groq extracted %d events from chunk (length=%d)", len(events), len(text_chunk))
            return events if events else _mock_events(text_chunk)
        except ImportError:
            logger.warning("groq package not installed; using mock. Run: pip install groq")
            return _mock_events(text_chunk)
        except Exception as e:
            logger.exception("Groq API error; falling back to mock: %s", e)
            return _mock_events(text_chunk)


llm_service = LLMService()
