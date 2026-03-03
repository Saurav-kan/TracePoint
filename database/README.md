# TracePoint Database

PostgreSQL + pgvector database for the AF-RAG evidence storage.

## Quick Start (Docker)

From the project root:

```bash
docker compose up -d
```

This starts PostgreSQL 16 with pgvector. The `init.sql` script runs automatically on first startup.

## Manual Setup

If you have PostgreSQL with pgvector installed locally:

1. Create a database: `createdb tracepoint`
2. Run the init script: `psql -d tracepoint -f init.sql`

Or use a GUI client (e.g., pgAdmin, DBeaver) to execute the contents of `init.sql`.

## Connection

- **Host:** localhost (or `db` when using Docker)
- **Port:** 5432
- **Database:** tracepoint
- **User/Password:** See `docker-compose.yml` or your local config

## Vector Index (HNSW)

The `init.sql` does **not** create an HNSW index on embeddings. Below ~10k vectors, linear search is faster than HNSW. Once you exceed 10k rows, run:

```bash
psql -d tracepoint -f database/add_hnsw_index.sql
```

## Schema

The `evidence_chunks` table stores evidence pieces with:
- `id` - Unique identifier
- `content` - Text content
- `embedding` - Vector (1536 dimensions for OpenAI embeddings)
- `label` - Evidence type tag (e.g., witness, gps, alibi)
- `reliability_score` - 0–1 weight (0.95 digital, 0.90 physical, 0.60 human)
- `timestamp` - When the event occurred / when data was collected (from the evidence)
- `source_document` - Optional document reference
- `additional_metadata` - JSONB for flexible fields (Officer ID, Room #, Weather, etc.)
- `created_at` - When the record was inserted (upload time)
