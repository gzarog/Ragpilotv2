# RAGpilot

RAGpilot is a local-first knowledge compiler and retrieval engine for software repositories and organizational documents. It has no web UI: it is consumed via a CLI, an MCP server, and an optional local REST API.

This repository is being built out in sequential, independently mergeable phases, each landing as its own pull request against `main`:

1. Production Foundation — CLI, configuration, source registry, SQLite storage, durable job queue, logging, health/doctor
2. Code Intelligence — Tree-sitter parsing, symbol/reference extraction, code graph, FTS5
3. Docling Document Pipeline — document ingestion, normalization, provenance, failure isolation
4. Unified Knowledge Model — entity normalization, cross-domain (code <-> docs) linking, confidence/evidence model
5. Retrieval — search, callers/callees, references, impact analysis, explore, query planner, context builder
6. MCP Server — stdio MCP server and agent-facing tools
7. Incremental Runtime — daemon, file watchers, polling, reconciliation, crash recovery
8. Operations — backup/restore, upgrade/rollback, metrics, packaging, release integrity
9. Optional Intelligence — vector retrieval, reranking, local embeddings, LLM provider abstraction

See `CONTRIBUTING.md` for development setup and `SECURITY.md` for the security policy.

## Quick start

```bash
pip install -e ".[dev]"
ragpilot init
ragpilot source add /path/to/a/repo/or/docs
ragpilot index
ragpilot status --json
ragpilot doctor
```

Phase 1 (this repository's current state) ships the CLI, layered configuration,
the source registry, SQLite storage with WAL and migrations, a durable job
queue with crash recovery, structured logging, and health checks. It records
file metadata and marks files indexed via a default "raw" processor — real
code and document parsing (Tree-sitter, Docling) land in later phases and hook
into the processor-registry extension point already in place.

## Design principles

- **Local-first**: source material and derived knowledge stay on disk by default.
- **AI-optional**: search, graph traversal, and impact analysis work without any LLM or network access.
- **Source of truth**: source files are authoritative; the RAGpilot database is rebuildable derived state.
- **Evidence-first**: every result traces back to a file, line/page, and section.
- **Fault isolation**: one malformed file must never stop the indexer or crash the daemon.
