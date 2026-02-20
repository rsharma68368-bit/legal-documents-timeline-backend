"""
User model for MongoDB (Beanie ODM).

Stores minimal user info; identity is Supabase (JWT).
We create/sync user in MongoDB on first authenticated request.
"""

from datetime import datetime
from typing import Optional

from beanie import Document, Indexed
from pydantic import Field


class User(Document):
    """
    User document. id is MongoDB ObjectId; supabase_id links to Supabase auth.
    """

    supabase_id: Indexed(str, unique=True)  # From JWT "sub" claim
    email: Optional[str] = None  # From JWT or profile
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"
        use_state_management = True

    class Config:
        json_schema_extra = {
            "example": {
                "supabase_id": "uuid-from-supabase",
                "email": "user@example.com",
                "created_at": "2025-01-01T00:00:00Z",
            }
        }
