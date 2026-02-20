"""
Document upload and status APIs.

POST /documents: upload PDF, store file, create record, trigger background processing.
GET /documents/{id}: return document status (and metadata) for the authenticated user.
"""

import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, UploadFile
from beanie import PydanticObjectId
from bson.dbref import DBRef

from app.api.auth import get_current_user
from app.config import get_settings
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.workers.document_processor import process_document

logger = logging.getLogger(__name__)
router = APIRouter()


def _ensure_upload_dir() -> Path:
    """Return upload directory path; caller may create if needed."""
    return Path(get_settings().upload_dir)


@router.post(
    "", 
    status_code=status.HTTP_201_CREATED,
    response_model=dict,
    summary="Upload a PDF document",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """
    Accept a PDF file, save it to disk, create a document record with status=pending,
    and schedule background processing. Response returns immediately with document id.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )

    upload_dir = _ensure_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    # Unique filename to avoid overwrites
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = upload_dir / safe_name

    # Stream file to disk (async would require aiofiles; we use sync write for simplicity)
    content = await file.read()
    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds {get_settings().max_upload_size_mb} MB",
        )
    file_path.write_bytes(content)
    logger.info("Saved upload to %s for user %s", file_path, current_user.id)

    # Create document record with status pending
    doc = Document(
        user_id=current_user,
        filename=file.filename or "document.pdf",
        file_path=str(file_path),
        status=DocumentStatus.PENDING,
    )
    await doc.insert()

    # Run processing in background so we can return 201 immediately
    # asyncio.create_task could also be used; BackgroundTasks is built into FastAPI
    # and runs after the response is sent, keeping request scope clean.
    background_tasks.add_task(process_document, doc.id)

    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "status": doc.status.value,
        "message": "Document uploaded; processing started.",
    }


@router.get(
    "",
    response_model=dict,
    summary="List documents",
)
async def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """
    Return all documents for the authenticated user (newest first).
    Use raw filter on user_id to avoid Beanie Link/aggregation issues.
    """
    # Query by user_id (Link may be stored as ObjectId or DBRef in MongoDB)
    docs = await Document.find({"user_id": current_user.id}).sort(-Document.created_at).to_list()
    if not docs:
        docs = await Document.find({"user_id": DBRef("users", current_user.id)}).sort(-Document.created_at).to_list()
    return {
        "documents": [
            {
                "id": str(d.id),
                "filename": d.filename,
                "status": d.status.value,
                "created_at": d.created_at.isoformat(),
                "error_message": d.error_message,
            }
            for d in docs
        ],
    }


@router.get(
    "/{document_id}",
    response_model=dict,
    summary="Get document status",
)
async def get_document_status(
    document_id: PydanticObjectId,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """
    Return document metadata and status. Only the owner can access.
    """
    doc = await Document.get(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    # Ensure ownership: compare linked user id (no fetch_link to avoid Beanie/Motor cursor bug)
    if doc.user_id.ref.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "status": doc.status.value,
        "created_at": doc.created_at.isoformat(),
        "error_message": doc.error_message,
    }
