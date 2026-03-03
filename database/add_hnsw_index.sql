-- Run this when you have more than 10,000 vectors.
-- Below 10k, linear search is faster; HNSW overhead only pays off at scale.
DO $$
BEGIN
  IF (SELECT count(*) FROM evidence_chunks) > 10000 THEN
    CREATE INDEX IF NOT EXISTS idx_evidence_chunks_embedding
      ON evidence_chunks
      USING hnsw (embedding vector_cosine_ops);
    RAISE NOTICE 'HNSW index created (table has > 10k vectors)';
  ELSE
    RAISE NOTICE 'Skipped: table has <= 10k vectors, linear search is faster';
  END IF;
END $$;
