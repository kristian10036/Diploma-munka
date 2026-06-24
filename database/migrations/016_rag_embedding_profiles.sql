-- Preserve existing vectors while allowing model-specific dimensions.
DROP INDEX IF EXISTS idx_embeddings_vector_hnsw;

ALTER TABLE embeddings
  ALTER COLUMN embedding_vector TYPE vector USING embedding_vector::vector,
  ADD COLUMN IF NOT EXISTS embedding_provider TEXT NOT NULL DEFAULT 'local_hash';

CREATE INDEX IF NOT EXISTS idx_embeddings_vector_hnsw_768
  ON embeddings USING hnsw ((embedding_vector::vector(768)) vector_cosine_ops)
  WHERE embedding_vector IS NOT NULL AND dimensions = 768;

CREATE INDEX IF NOT EXISTS idx_embeddings_vector_hnsw_1024
  ON embeddings USING hnsw ((embedding_vector::vector(1024)) vector_cosine_ops)
  WHERE embedding_vector IS NOT NULL AND dimensions = 1024;

CREATE INDEX IF NOT EXISTS idx_embeddings_profile
  ON embeddings (embedding_provider, embedding_model, dimensions);

DROP INDEX IF EXISTS idx_embeddings_chunk_model_unique;
CREATE UNIQUE INDEX IF NOT EXISTS idx_embeddings_chunk_provider_model_unique
  ON embeddings (chunk_id, embedding_provider, embedding_model);
