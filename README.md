# Legal Document Timeline Extraction API

Production-quality FastAPI backend that uploads PDFs, extracts text, and produces a **timeline of events** (dates, descriptions, parties, significance) using an LLM. Built with clean architecture, async I/O, and a mock LLM layer that you can replace with a real provider.

---

## Project Overview

- **Purpose**: Accept legal (or any) PDF documents, run background extraction of timeline events, and expose status and timeline via REST API.
- **Auth**: Supabase JWT only (no Supabase DB). JWTs are validated with your project secret; users are created/synced in MongoDB on first request.
- **Processing**: Upload → save file → create document record (`pending`) → background task extracts text, chunks it, calls LLM (mock by default), merges/sorts events, saves timeline and sets status to `completed` or `failed`.

---

## Architecture

- **Clean separation**: Routes (API) → Services (PDF, LLM, timeline logic) → Workers (orchestration) → Models (Beanie/MongoDB).
- **Async**: FastAPI + Motor + Beanie for non-blocking DB and HTTP; CPU-bound PDF work runs in a thread pool via `asyncio.to_thread`.
- **Background jobs**: Handled with FastAPI `BackgroundTasks` (or you can switch to `asyncio.create_task()`). No separate queue (e.g. Celery) in this version to keep the stack simple.

---

## Request Flow

1. **Upload**  
   `POST /api/documents` with `Authorization: Bearer <supabase_jwt>` and a PDF file.  
   → Validate JWT → create/sync user in MongoDB → save file under `uploads/` → create `Document` with `status=pending` → enqueue background task → return `201` with `id` and `status`.

2. **Background worker**  
   For the new document: set `status=processing` → extract text (PyPDF2 in thread) → chunk (e.g. 10k chars) → for each chunk call LLM service (mock returns sample events) → merge and sort events by date → save `Timeline` → set `status=completed` or `failed` (with `error_message` on failure).

3. **Status**  
   `GET /api/documents/{id}` (with JWT) → return document metadata and `status` (and `error_message` if failed).

4. **Timeline**  
   `GET /api/documents/{id}/timeline` (with JWT) → return list of events for that document (404 if not ready or not found).

---

## How Background Processing Works

- **Why background**: PDF parsing and LLM calls can take seconds; we don’t want the upload request to block until processing is done.
- **Mechanism**: FastAPI’s `BackgroundTasks.add_task(process_document, doc.id)` runs `process_document` after the response is sent. The task runs inside the same process and event loop.
- **Trade-off**: No durability (process crash = task lost). For production at scale you’d add a queue (e.g. Redis + Celery, or a task queue that persists jobs).

---

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `MONGODB_URL` | MongoDB connection string | `mongodb://localhost:27017` |
| `MONGODB_DATABASE` | Database name | `legal_timeline_db` |
| `SUPABASE_URL` | Supabase project URL (optional, for reference) | `https://xxx.supabase.co` |
| `SUPABASE_JWT_SECRET` | Supabase JWT secret (project secret) for verifying tokens | From Supabase Dashboard → Settings → API |
| `UPLOAD_DIR` | Directory for stored PDFs (relative or absolute) | `uploads` |
| `MAX_UPLOAD_SIZE_MB` | Max PDF size in MB | `50` |
| `DEBUG` | Enable debug logging | `false` |

Create a `.env` in the `backend/` directory (or set env vars in the shell). Supabase JWT secret is required for auth.

---

## API Documentation

- **Swagger UI**: After running the app, open `http://localhost:8000/docs`.
- **ReDoc**: `http://localhost:8000/redoc`.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/documents` | Upload PDF (body: form-data with `file`). Requires `Authorization: Bearer <jwt>`. |
| `GET` | `/api/documents/{document_id}` | Get document status. Requires auth; only owner. |
| `GET` | `/api/documents/{document_id}/timeline` | Get timeline events. Requires auth; only owner. |

All document/timeline endpoints require a valid Supabase JWT in the `Authorization` header.

---

## Design Decisions

- **Supabase JWT only**: Auth is validated with the project JWT secret; user state lives in MongoDB so the backend stays independent of Supabase DB.
- **Mock LLM first**: A dedicated `LLMService` returns fake events so the pipeline (upload → chunk → “LLM” → merge → save) is testable without API keys. Swap in a real LLM in `app/services/llm_service.py`.
- **Local file storage**: PDFs are written to `uploads/`. For production you’d typically use object storage (S3, GCS) and store a reference in `Document.file_path`.
- **BackgroundTasks**: Keeps the implementation simple and avoids extra infra. For retries and durability, replace with a proper job queue.

---

## Trade-offs

| Choice | Benefit | Trade-off |
|--------|---------|-----------|
| `BackgroundTasks` | No extra services, easy to run | No retries, no persistence across restarts |
| Local `uploads/` | Simple, no cloud dependency | Not suitable for multi-instance or serverless |
| Mock LLM | No API cost, fast iteration | No real extraction until you plug in a real LLM |
| Beanie + Motor | Async MongoDB, type-safe models | Tied to MongoDB |

---

## Extending with a Real LLM

1. Open `app/services/llm_service.py`.
2. In `extract_events_from_chunk`, replace the mock logic with:
   - A call to your LLM API (OpenAI, Anthropic, etc.) with a prompt that asks for structured events (date, description, involved_parties, significance).
   - Parse the response (e.g. JSON or structured output) into `List[Event]`.
3. Add API keys via config (e.g. `OPENAI_API_KEY` in `app/config.py`) and use them in the service. Keep the same `async` interface so the worker does not need to change.

---

## Folder Structure

```
backend/
├── app/
│   ├── main.py          # FastAPI app, lifespan, CORS, router includes
│   ├── config.py        # Pydantic Settings (env vars)
│   ├── database.py      # Beanie + Motor init
│   ├── api/
│   │   ├── auth.py      # JWT validation, get_current_user dependency
│   │   ├── documents.py # POST upload, GET status
│   │   └── timeline.py  # GET timeline by document id
│   ├── models/
│   │   ├── user.py      # User (Beanie)
│   │   ├── document.py  # Document, DocumentStatus (Beanie)
│   │   └── timeline.py  # Timeline, Event (Beanie + Pydantic)
│   ├── services/
│   │   ├── pdf_service.py      # PDF text extraction, chunking
│   │   ├── llm_service.py      # LLM interface (mock implementation)
│   │   └── timeline_service.py # Merge and sort events
│   ├── workers/
│   │   └── document_processor.py # Background pipeline: PDF → chunks → LLM → save
│   └── utils/                  # Optional helpers
├── uploads/             # Created at runtime; stored PDFs
├── requirements.txt
└── README.md
```

---

## How to Run

1. **Python**: 3.11+.
2. **MongoDB**: Running locally or remote; set `MONGODB_URL` and `MONGODB_DATABASE`.
3. **Install**:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```
4. **Environment**: Set `SUPABASE_JWT_SECRET` (and optionally other vars) in `.env` or the shell.
5. **Start**:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
6. **Try**:  
   - `GET /docs` for Swagger.  
   - `POST /api/documents` with a PDF and `Authorization: Bearer <your_supabase_jwt>`.  
   - Poll `GET /api/documents/{id}` then `GET /api/documents/{id}/timeline` when status is `completed`.

---

## License

Use as needed for your project.
