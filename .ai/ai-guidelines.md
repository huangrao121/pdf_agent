# Project Spec: PDF Reader + Chatbot + Markdown Notebook (RAG-first Learning Workspace)

## 1. Project Vision

Build a focused learning workspace where users:
- Primarily **read PDF documents (books, papers, manuals)**
- Can **ask contextual questions directly while reading**
- Can **write structured Markdown notes linked to the source**
- Always receive **answers grounded in the document with citations**
- Have a system that is extensible toward external tools/APIs later

This is **not a generic chatbot**.  
This is a **document-grounded learning and thinking environment**.

Core principle:
> Reading is primary. Chat and notes are augmentations of reading, not replacements.

---

## 2. Core Features

### 2.1 PDF Reader
- Upload PDF per workspace
- View PDF with page navigation
- Select text inside PDF
- Highlights and anchors tied to exact location (page + offset/bbox)
- Clickable citations jump to the correct page + highlight

### 2.2 Chatbot (RAG-based, document grounded)
- Ask questions while reading
- "Selection-first" behavior:
  - If user selected text, the answer must prioritize explaining that text
- Otherwise fallback to:
  - Vector search over document chunks (Neo4j)
- Answers must:
  - Be grounded in retrieved chunks
  - Include citations (doc_id, page, chunk_id)
- If evidence is insufficient:
  - The assistant should say: "Not found in the document"

### 2.3 Markdown Notebook
- Each user/workspace has notes
- Notes written in Markdown
- Notes can contain:
  - User text
  - AI-generated summaries
  - Q&A blocks
  - Citation blocks (anchors) referencing PDF chunks
- Clicking a citation jumps back to the exact PDF location

### 2.4 Ingestion Pipeline
- Upload PDF
- Parse text + extract structure
- Chunk text deterministically
- Store chunks + metadata in Postgres
- Generate embeddings
- Store vector embeddings in Neo4j
- Fully idempotent and re-runnable

---

## 3. Architecture Overview

### High-level Architecture

- FastAPI Monolithic Backend (modular internally)
- Async Worker for ingestion jobs
- Postgres = source of truth
- Neo4j = semantic index (vector + future graph)
- Object Storage = PDF files
- Frontend (later): PDF Viewer + Chat panel + Notes panel



---

## 4. Tech Stack

### Backend
- Python 3.13
- FastAPI
- Pydantic
- SQLAlchemy or SQLModel
- psycopg / asyncpg
- Langchain / Langgraph

### Databases
- PostgreSQL 16+
  - Business data
  - Documents
  - Chunks
  - Notes
  - Anchors
  - Messages
  - Jobs
- Neo4j 5.x+
  - Chunk nodes
  - Document nodes
  - Vector index on Chunk.embedding

### AI / ML
- Embeddings: OpenAI / local embedding model
- LLM: OpenAI / Anthropic / local model
- RAG orchestration written manually (not LangChain dependency-heavy)

### Storage
- local dev filesystem / (Azure blob for future development)

### Optional Later
- Redis (cache in the future)
- External tool plugins (web search, APIs)
- GraphRAG (using Neo4j edges)

---

## 5. Data Model Summary

### Postgres Tables
- docs
- chunks
- notes
- anchors
- chat_sessions
- messages
- jobs

Postgres is the **single source of truth**.  
Neo4j is **derivable index data only**.

### Neo4j Nodes
- (:Document {doc_id, workspace_id, title, file_sha256})
- (:Chunk {chunk_id, doc_id, workspace_id, page_start, text, embedding})

Relationships:
- (:Document)-[:HAS_CHUNK]->(:Chunk)

Vector index:
- On Chunk.embedding using cosine similarity

---

## 6. Core Pipelines

### 6.1 Ingestion Pipeline
1. User uploads PDF
2. Store PDF to object storage
3. Create docs row in Postgres
4. Worker picks job:
   - Parse PDF
   - Chunk text
   - Compute text_sha256
   - Deterministically generate chunk_id
   - Upsert chunks into Postgres
   - Generate embeddings
   - Upsert Document + Chunk nodes into Neo4j
5. Mark doc as READY

Must be:
- Idempotent
- Safe to retry
- Rebuildable at any time

---

### 6.2 Chat Pipeline
1. User asks question
2. If selection exists:
   - Include selected text as primary context
3. Else:
   - Embed query
   - Neo4j vector search top-k chunks
4. Assemble context
5. Generate answer using LLM
6. Attach citations
7. Store messages + citations in Postgres

Assistant behavior rule:
> Never answer outside document evidence unless explicitly allowed in future.

---

### 6.3 Notes Pipeline
- User edits Markdown freely
- When inserting AI output:
  - System creates anchors referencing chunks/pages
- Notes remain fully user-controlled
- Notes may later become searchable knowledge too

---

## 7. Design Principles

### Product Principles
- Reading > Chat > Notes (in that priority order)
- Grounded answers only
- Citations are mandatory
- User always controls their knowledge

### Engineering Principles
- Postgres = truth, Neo4j = index
- Everything reproducible (rebuild index anytime)
- Deterministic chunking + chunk_id
- Clear module boundaries (even inside monolith)
- Prefer explicit orchestration over black-box frameworks

---

## 8. Non-goals (for now)
- No GraphRAG required initially
- No web search / external tools by default
- No over-engineered microservices
- No speculative "autonomous agent" behavior

---

## 9. Future Extensions (Designed but not required now)
- External tool plugins (web search, APIs)
- Notes as secondary retrieval source
- Graph edges between chunks (true GraphRAG)
- Multi-document comparison
- Flashcards / spaced repetition
- Collaboration on notes
- Go-based orchestration layer if system grows

---

The system behaves more like:
> A disciplined research assistant inside the book  
not  
> A generic chatbot with internet knowledge

