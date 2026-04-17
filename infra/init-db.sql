-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- n8n and langfuse will create their own tables on first boot
