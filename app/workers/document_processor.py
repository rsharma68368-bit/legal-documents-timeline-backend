"""
Background document processing worker.

Runs as a FastAPI BackgroundTask after upload: extracts text from PDF, chunks it,
calls LLM to extract events, merges/sorts, and saves timeline.

Why background: PDF parsing and LLM calls can take seconds. If we did this in the
request handler, the client would wait and connections could time out. By running
in the background we return 201 immediately and let the client poll GET /documents/{id}
for status and GET /documents/{id}/timeline for results.

Why separate worker module: Keeps route handlers thin; all pipeline logic and error
handling (status=failed, error_message) lives in one place and is easier to test.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from beanie import PydanticObjectId

from app.models.document import Document, DocumentStatus
from app.models.timeline import Event, Timeline
from app.services.llm_service import llm_service
from app.services.pdf_service import chunk_text, extract_text_from_pdf
from app.services.timeline_service import merge_and_sort_events

logger = logging.getLogger(__name__)


async def process_document(document_id: PydanticObjectId) -> None:
    """
    Full pipeline for one document: extract text -> chunk -> LLM -> merge -> save.
    Updates document status to processing, then completed or failed.
    """
    doc: Optional[Document] = await Document.get(document_id)
    if not doc:
        logger.error("Document not found: %s", document_id)
        return
    if doc.status != DocumentStatus.PENDING:
        logger.info("Document %s already in status %s; skipping.", document_id, doc.status)
        return

    # Mark as processing so GET /documents/{id} shows progress
    doc.status = DocumentStatus.PROCESSING
    await doc.save_changes()
    logger.info("Started processing document %s", document_id)

    try:
        # PDF extraction is CPU-bound and blocking; run in thread pool to avoid blocking event loop
        raw_text = await asyncio.to_thread(extract_text_from_pdf, doc.file_path)
        if not raw_text or not raw_text.strip():
            raise ValueError("No text extracted from PDF")

        chunks = chunk_text(raw_text, chunk_size=10_000)
        logger.info("Document %s: %d chunks", document_id, len(chunks))

        # Call LLM for each chunk (async; I/O when using real LLM)
        all_event_lists: list[list[Event]] = []
        for i, chunk in enumerate(chunks):
            events = await llm_service.extract_events_from_chunk(chunk)
            all_event_lists.append(events)
            logger.debug("Chunk %d: %d events", i + 1, len(events))

        merged = merge_and_sort_events(all_event_lists)

        # Persist timeline and link to document
        timeline = Timeline(document_id=doc, events=merged)
        await timeline.insert()

        doc.status = DocumentStatus.COMPLETED
        doc.error_message = None
        await doc.save_changes()
        logger.info("Document %s completed; %d events saved.", document_id, len(merged))

    except FileNotFoundError as e:
        logger.exception("File not found for document %s: %s", document_id, e)
        doc.status = DocumentStatus.FAILED
        doc.error_message = "PDF file not found"
        await doc.save_changes()
    except Exception as e:
        logger.exception("Processing failed for document %s: %s", document_id, e)
        doc.status = DocumentStatus.FAILED
        doc.error_message = str(e)[:500]  # Limit length stored
        await doc.save_changes()
