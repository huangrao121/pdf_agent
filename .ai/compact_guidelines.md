# Project Spec (Compact)

## Vision
Build a document-grounded learning workspace:
- Read PDFs
- Ask contextual questions
- Write Markdown notes linked to source
- Answers must be evidence-based with citations

Not a general chatbot. Reading is primary.

---

## Core Features
### PDF Reader
- Upload/view PDFs
- Text selection
- Clickable citations → jump to page + highlight

### Chat (RAG-first)
- Selection-first: selected text overrides retrieval
- Otherwise: vector search over chunks
- Every answer must include citations (doc_id/page/chunk_id)
- If evidence insufficient → say “not found in document”

### Notes (Markdown)
- Free-form Markdown notes
- Can insert AI Q&A / summaries
- Citation blocks (anchors) link notes → PDF chunks

### Ingestion
- Parse PDF → chunk → embed → index
- Fully idempotent & rebuildable

---

## Architecture
Single FastAPI app (modular) + async worker.

- FastAPI (API + orchestration)
- Worker (PDF parse, chunk, embed, index)
- Postgres = source of truth
- Neo4j = vector/semantic index
- Object storage = PDFs

Neo4j data must always be rebuildable from Postgres.

---

## Tech Stack
- Python 3.12 + FastAPI + Pydantic
- PostgreSQL (docs, chunks, notes, anchors, messages, jobs) + SQLAlchemy
- Neo4j (Document + Chunk + vector index)
- OpenAI/other LLM + embedding APIs
- No LangChain dependency requirement

---

## Data Model (Conceptual)
Postgres:
- docs, chunks, notes, anchors, chat_sessions, messages, jobs

Neo4j:
- (:Document {doc_id, workspace_id, ...})
- (:Chunk {chunk_id, doc_id, embedding, text, page...})
- (Document)-[:HAS_CHUNK]->(Chunk)
- Vector index on Chunk.embedding

---

## Pipelines
### Ingestion
Upload → parse → deterministic chunks → PG upsert → embed → Neo4j upsert → READY  
Must be safe to retry anytime.

### Chat
Selection → else retrieval → grounded answer → citations → store message

Rule:
> Never answer beyond document evidence.

### Notes
Markdown editable by user  
Anchors connect notes ↔ chunks/pages

---

## Design Principles
- Postgres = truth, Neo4j = index
- Deterministic chunk_id
- Reproducible ingestion
- Explicit orchestration (no black-box agents)
- Grounded answers only

---

## Non-goals (now)
- No GraphRAG by default
- No external web/tools
- No microservices
- No heavy agent framework

---

## Assistant Behavior Contract
1. Prefer selected text
2. Else retrieve evidence
3. Answer only from evidence
4. Always cite
5. If missing evidence → admit it
6. Never hallucinate document content
