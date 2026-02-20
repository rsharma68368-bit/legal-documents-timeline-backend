"""
LLM service layer for timeline event extraction.

Why separate service: The worker (document_processor) only knows it calls
extract_events_from_chunk(text). How that is implemented (mock vs OpenAI vs Anthropic)
is isolated here. When you add a real LLM you only touch this file and config; routes
and workers stay unchanged. This is the dependency inversion principle in practice.
"""

import logging
from typing import List

from app.models.timeline import Event

logger = logging.getLogger(__name__)


class LLMService:
    """
    Encapsulates all LLM calls. Use async methods so the event loop is not blocked
    during network I/O when we switch to a real API.
    """

    async def extract_events_from_chunk(self, text_chunk: str) -> List[Event]:
        """
        Extract timeline events from a single text chunk.
        Mock: returns placeholder events. Replace with real LLM call later.
        """
        # In production: call OpenAI/Anthropic with a prompt like
        # "From the following legal document text, extract events with date, description, involved_parties, significance."
        # and parse response into List[Event].
        logger.debug("Mock LLM processing chunk length=%d", len(text_chunk))
        # Return mock events so the pipeline still runs end-to-end
        return [
            Event(
                date="2023-01-15",
                description="Sample event extracted from document (mock).",
                involved_parties=["Party A", "Party B"],
                significance="Mock significance for testing.",
            ),
        ]


# Singleton for dependency injection; can be replaced with a factory if needed
llm_service = LLMService()
