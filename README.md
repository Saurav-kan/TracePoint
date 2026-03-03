# TracePoint

Fact-checking RAG application for law enforcement investigations. Detects contradictions across witness statements, digital logs, and physical evidence.

## Architecture

- **Frontend:** Next.js + React
- **Backend:** FastAPI
- **Database:** PostgreSQL + pgvector (cases + evidence)
- **Orchestration:** LangGraph (planned)

## Setup

### 1. Database

Start PostgreSQL with pgvector:

```bash
docker compose up -d
```

See [database/README.md](database/README.md) for manual setup.

### 2. Backend (Python)

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Unix
pip install -r backend/requirements.txt
```

Copy `backend/.env.example` to `backend/.env` and adjust if needed.

Run the API:

```bash
uvicorn app.main:app --reload --app-dir backend
```

API docs at http://localhost:8000/docs

**Case + ingestion flow:**

1. **Create case header**

   ```bash
   curl -X POST http://localhost:8000/cases \
     -H "Content-Type: application/json" \
     -d '{"title":"Case 001","case_brief_text":"..."}'
   ```

   Response:

   ```json
   { "case_id": "<uuid>", "status": "created" }
   ```

2. **Ingest evidence for that case** (Docling parsing + embeddings + evidence clerk):

   ```bash
   curl -X POST http://localhost:8000/ingest \
     -H "Content-Type: application/json" \
     -d '{"text":"... evidence ...","label":"witness","case_id":"<uuid>"}'
   ```

   Response:

   ```json
   { "case_id": "<uuid>", "chunks_created": N }
   ```

3. **Request planner tasks for a fact-to-check**

   ```bash
   curl -X POST http://localhost:8000/planner/plan \
     -H "Content-Type: application/json" \
     -d '{"case_id":"<uuid>","fact_to_check":"The suspect was at the store at 23:00"}'
   ```

   Response (shape):

   ```json
   {
     "case_id": "<uuid>",
     "fact_to_check": "...",
     "friction_summary": { "has_friction": true, "description": "..." },
     "search_boundary": { "start_time": "...", "end_time": "..." },
     "tasks": [
       {
         "type": "VERIFICATION",
         "question_text": "...",
         "vector_query": "...",
         "metadata_filter": { "label": "gps_log" }
       }
     ]
   }
   ```

### 3. Frontend

```bash
cd frontend && npm install && npm run dev
```

App at http://localhost:3000

## Project Structure

```
TracePoint/
├── frontend/       # Next.js + React
├── backend/        # FastAPI
├── database/       # PostgreSQL schema + init scripts
└── plan.md         # Technical specification
```
