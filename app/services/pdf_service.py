"""
PDF text extraction service.

Uses PyPDF2 to extract raw text from PDF files.
Extraction is CPU-bound; we run it in a thread pool to avoid blocking the event loop.
"""

import logging
from pathlib import Path
from typing import List

from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_path: str | Path) -> str:
    """
    Extract all text from a PDF file.
    This is blocking I/O and CPU work; call via asyncio.to_thread in the worker.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    reader = PdfReader(str(path))
    parts: List[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n".join(parts)


def chunk_text(text: str, chunk_size: int = 10_000) -> List[str]:
    """
    Split text into chunks of roughly chunk_size characters.
    We use 10k character chunks so that each piece fits typical LLM context limits
    while still containing enough context for date/event extraction.
    """
    if not text or chunk_size <= 0:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        # Avoid cutting in the middle of a word if possible
        if end < len(text):
            last_space = text.rfind(" ", start, end + 1)
            if last_space > start:
                end = last_space + 1
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]
