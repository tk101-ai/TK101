-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Separate database for Langfuse to avoid schema conflicts
CREATE DATABASE langfuse;

-- n8n uses the default tk101 database
-- langfuse uses its own langfuse database
