-- Enable pgvector as superuser (app role cannot CREATE EXTENSION).
CREATE EXTENSION IF NOT EXISTS vector;
