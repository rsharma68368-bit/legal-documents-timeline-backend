"""
Timeline and Event models.

Timeline holds the list of extracted events for a document.
Event is an embedded schema (no separate collection).
"""

from typing import List

from beanie import Document, Link
from pydantic import BaseModel, Field

from app.models.document import Document as DocumentModel


class Event(BaseModel):
    """
    Single timeline event extracted from document text.
    Used as embedded document inside Timeline.events.
    """

    date: str  # ISO date string for sorting and display
    description: str
    involved_parties: List[str] = Field(default_factory=list)
    significance: str = ""

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2023-06-15",
                "description": "Contract signed between parties.",
                "involved_parties": ["Party A", "Party B"],
                "significance": "Effective date of agreement.",
            }
        }


class Timeline(Document):
    """
    One timeline per document. events are sorted by date after extraction.
    """

    document_id: Link[DocumentModel]
    events: List[Event] = Field(default_factory=list)

    class Settings:
        name = "timelines"
        use_state_management = True

    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "doc_id_here",
                "events": [],
            }
        }
