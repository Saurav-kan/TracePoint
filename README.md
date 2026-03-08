# TracePoint

Fact-checking RAG application for law enforcement investigations. Detects contradictions across witness statements, digital logs, and physical evidence.

## Architecture

- **Frontend:** Next.js + React + Tailwind CSS
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL + pgvector (cases & evidence)
- **Agents & Orchestration:** Custom 3-Agent Pipeline (Planner → Researcher → Judge) with Gatekeeper validation
- **Models:** Supports OpenAI, Google Gemini, Groq, and SiliconFlow (as fallback)

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

3. **Run the full investigation workflow (Planner → Researcher → Judge)**

   ```bash
   curl -X POST http://localhost:8000/workflow/run \
     -H "Content-Type: application/json" \
     -d '{"case_id":"<uuid>","fact_to_check":"The suspect was at the store at 23:00"}'
   ```

   Response (shape) from the Judge Agent:

   ```json
   {
     "case_id": "<uuid>",
     "fact_to_check": "...",
     "tasks": [
       {
         "question_text": "...",
         "answer": "...",
         "sufficient_evidence": true,
         "confidence": 0.8,
         "key_facts": []
       }
     ],
     "overall_verdict": {
       "claim": "...",
       "verdict": "likely_true",
       "rationale": "...",
       "supporting_facts": [],
       "contradicting_facts": []
     },
     "gatekeeper_passed": true,
     "refinement_suggestion": null
   }
   ```

   _Note: The workflow encompasses Friction Detection, task decomposition (Planner), semantic vector searches (Researcher), and per-task + holistic evidence synthesis (Judge)._

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
