"""
Timeline aggregation and persistence.

Merges events from multiple chunks, sorts by date, and saves to MongoDB.
"""

import logging
from typing import List

from app.models.timeline import Event

logger = logging.getLogger(__name__)


def merge_and_sort_events(all_events: List[List[Event]]) -> List[Event]:
    """
    Merge event lists from all chunks and sort by date (ISO string comparison).
    Deduplication could be added here (e.g. by date+description) if needed.
    """
    merged: List[Event] = []
    for events in all_events:
        merged.extend(events)
    merged.sort(key=lambda e: e.date)
    return merged
