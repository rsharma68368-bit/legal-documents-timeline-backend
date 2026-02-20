"""
Timeline API: return extracted events for a document.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from beanie import PydanticObjectId
from bson.dbref import DBRef

from app.api.auth import get_current_user
from app.models.document import Document
from app.models.timeline import Event, Timeline
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/{document_id}/timeline",
    response_model=dict,
    summary="Get timeline for a document",
)
async def get_document_timeline(
    document_id: PydanticObjectId,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """
    Return the extracted timeline (list of events) for the given document.
    Only the document owner can access. Returns 404 if document or timeline not found.
    """
    doc = await Document.get(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    # Ownership check without fetch_link (avoids Beanie/Motor aggregate cursor bug)
    if doc.user_id.ref.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    # Find timeline: Beanie Link may store ObjectId or DBRef in MongoDB
    timeline = await Timeline.find_one(Timeline.document_id == doc.id)
    if not timeline:
        timeline = await Timeline.find_one({"document_id": doc.id})
    if not timeline:
        # Beanie sometimes stores Link as DBRef(ref_collection, id)
        timeline = await Timeline.find_one({"document_id": DBRef("documents", doc.id)})
    if not timeline:
        # Document is completed but no timeline: return empty events so UI can show "No events"
        if doc.status.value == "completed":
            logger.warning("Document %s is completed but no timeline record found; returning empty events.", document_id)
            return {"document_id": str(doc.id), "events": []}
        logger.info("No timeline for document_id=%s (status=%s)", document_id, doc.status)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Timeline not ready yet or document still processing",
        )
    return {
        "document_id": str(doc.id),
        "events": [e.model_dump() for e in timeline.events],
    }
