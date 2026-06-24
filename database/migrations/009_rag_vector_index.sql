CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE embeddings
  ADD COLUMN IF NOT EXISTS embedding_vector vector(768),
  ADD COLUMN IF NOT EXISTS content_sha256 CHAR(64),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE UNIQUE INDEX IF NOT EXISTS idx_embeddings_chunk_model_unique
  ON embeddings (chunk_id, embedding_model);

CREATE INDEX IF NOT EXISTS idx_embeddings_vector_hnsw
  ON embeddings USING hnsw (embedding_vector vector_cosine_ops)
  WHERE embedding_vector IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_index
  ON document_chunks (document_id, chunk_index);

CREATE INDEX IF NOT EXISTS idx_documents_type_created
  ON documents (document_type, created_at DESC);
