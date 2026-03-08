-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;
-- UUID generation for cases
CREATE EXTENSION IF NOT EXISTS pgcrypto;
-- PostGIS: not available in pgvector image; use postgis/postgis + pgvector for geo.
-- Store coords in additional_metadata JSONB until then.

CREATE TABLE evidence_chunks (
    id BIGSERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(1536),

    -- Investigative Metadata
    label VARCHAR(100) NOT NULL, -- e.g., 'witness', 'gps', 'alibi'
    reliability_score DECIMAL(3,2) NOT NULL DEFAULT 0.5
        CHECK (reliability_score >= 0 AND reliability_score <= 1),

    -- Temporal Data: when the event occurred / when data was collected (from the evidence)
    timestamp TIMESTAMPTZ,

    -- Source Tracking
    source_document VARCHAR(255),

    -- Flexible metadata for Officer ID, Room #, Weather, etc.
    additional_metadata JSONB DEFAULT '{}',

    -- When the record was inserted (upload time)
    created_at TIMESTAMPTZ DEFAULT now()
);

-- No HNSW index here: linear search is faster below ~10k vectors.
-- Run database/add_hnsw_index.sql once you have more than 10k rows.

-- GIN index for filtering by metadata (Case ID, Officer, etc.)
CREATE INDEX idx_evidence_chunks_metadata ON evidence_chunks USING GIN (additional_metadata);

-- Filtering indexes
CREATE INDEX idx_evidence_chunks_label ON evidence_chunks(label);
CREATE INDEX idx_evidence_chunks_timestamp ON evidence_chunks(timestamp);

-- Cases header table
CREATE TABLE cases (
    case_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    case_brief_text TEXT NOT NULL,
    brief_embedding vector(1536),
    target_subject_name TEXT,
    crime_timestamp_start TIMESTAMPTZ,
    crime_timestamp_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'active'
);

-- Link evidence to cases
ALTER TABLE evidence_chunks
    ADD COLUMN case_id UUID REFERENCES cases(case_id) ON DELETE CASCADE;

CREATE INDEX idx_evidence_case_id ON evidence_chunks(case_id);

-- Case briefs (multiple summaries per case)
CREATE TABLE IF NOT EXISTS case_briefs (
    id BIGSERIAL PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'Case Summary',
    brief_text TEXT NOT NULL,
    brief_embedding vector(1536),
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Investigation logs (persisted pipeline runs)
CREATE TABLE IF NOT EXISTS investigation_logs (
    id BIGSERIAL PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    claim TEXT NOT NULL,
    effort_level VARCHAR(10) NOT NULL DEFAULT 'low',
    verdict VARCHAR(50) NOT NULL,
    result_payload JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_investigation_logs_case_id ON investigation_logs(case_id);
