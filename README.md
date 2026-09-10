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
ragpilot symbol MyClass
ragpilot callers my_function
ragpilot callees my_function
ragpilot references MyClass
ragpilot docs --json
```

Phase 1 shipped the CLI, layered configuration, the source registry, SQLite
storage with WAL and migrations, a durable job queue with crash recovery,
structured logging, and health checks, plus the processor-registry extension
point later phases hook into.

Phase 2 adds Tree-sitter-based code intelligence: `ragpilot index` now
parses recognized source files, extracts classes/interfaces/structs/enums,
functions/methods/properties/fields, imports, inheritance, and calls into a
normalized entity/relationship graph (stored alongside an FTS5 index over
symbol names), and exposes it read-only via
`ragpilot symbol|callers|callees|references`. Fully supported languages:
**Python, JavaScript, TypeScript/TSX, Go, Java, Rust, C#**. A recognized code
file with no grammar wired up yet (e.g. `.rb`, `.sql`, `.sh`) still indexes
successfully, just without extracted entities. A file that fails to parse is
isolated and recorded as failed, exactly like Phase 1's file-level fault
isolation, and never aborts the run.

Phase 3 (this repository's current state) adds a Docling-backed document
pipeline: `ragpilot index` now also converts document-kind files --
**PDF, DOCX, PPTX, XLSX, HTML, Markdown, TXT, EML** -- into a normalized
heading/paragraph/table structure with page and heading-path provenance on
every unit, stored alongside an FTS5 index over headings/body text/title,
and exposed read-only via `ragpilot docs`. OCR, images, audio/video,
OpenDocument, EPUB, and VLM pipelines are out of scope for this phase. A
corrupt or unsupported document is isolated and recorded as failed (or, for
an extension Phase 3 doesn't convert yet, indexed without derived content)
rather than aborting the run; a PDF over `documents.max_pages` is marked
`skipped_limit`. Docling's PDF pipeline downloads layout/table-structure
model weights on first use -- tests that exercise it are marked
`docling_pdf` and excluded from the default test run (see CONTRIBUTING.md).
Cross-domain (code <-> document) linking and the MCP server land in later
phases.

## Design principles

- **Local-first**: source material and derived knowledge stay on disk by default.
- **AI-optional**: search, graph traversal, and impact analysis work without any LLM or network access.
- **Source of truth**: source files are authoritative; the RAGpilot database is rebuildable derived state.
- **Evidence-first**: every result traces back to a file, line/page, and section.
- **Fault isolation**: one malformed file must never stop the indexer or crash the daemon.
