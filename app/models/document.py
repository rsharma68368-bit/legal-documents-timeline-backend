"""
Document model for uploaded PDFs.

Tracks file path, status through processing pipeline, and ownership.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class DocumentStatus(str, Enum):
    """Lifecycle states of a document in the pipeline."""

    PENDING = "pending"  # Uploaded, not yet picked by worker
    PROCESSING = "processing"  # Worker is extracting text / calling LLM
    COMPLETED = "completed"  # Timeline saved successfully
    FAILED = "failed"  # Error during processing


class Document(Document):
    """
    Represents an uploaded PDF and its processing state.
    user_id links to the User who uploaded it.
    """

    user_id: Link[User]
    filename: str
    file_path: str  # Path relative to app root or absolute
    status: DocumentStatus = DocumentStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None  # Set when status is FAILED

    class Settings:
        name = "documents"
        use_state_management = True

    class Config:
        json_schema_extra = {
            "example": {
                "filename": "contract.pdf",
                "file_path": "uploads/abc123.pdf",
                "status": "pending",
                "created_at": "2025-01-01T00:00:00Z",
            }
        }
