# RAGpilot

A local-first knowledge compiler and retrieval engine for software repositories and organizational documents.

## What is RAGpilot

RAGpilot turns a folder of source code and documents into a queryable, evidence-backed knowledge base that lives entirely on your machine. Point it at a repository and a docs folder, index them, and then ask questions like "what breaks if `SettlementService` changes?" or "who calls `bark_loudly`?" and get answers traced back to exact files, lines, and pages — not guesses.

It has no web UI. You use it three ways:

- **CLI** — for humans, scripts, and CI (every command supports `--json`)
- **MCP server** (`ragpilot serve --mcp`) — for AI coding agents (Claude Code, Cursor, etc.) that speak the [Model Context Protocol](https://modelcontextprotocol.io)
- **A daemon** (`ragpilot watch` / `ragpilot daemon start`) that keeps the knowledge base current as files change

Two things make it different from a typical embeddings-only RAG tool:

- **Deterministic by default.** Symbol lookup, call graphs, full-text search, and cross-domain code↔doc linking all work with zero network access and zero LLM calls. Semantic (embedding-based) search and LLM-generated answers are opt-in extras layered on top, not the foundation.
- **Evidence-first.** Every result — a caller, a linked document, a search hit — carries a confidence tier (`EXACT`/`HIGH`/`MEDIUM`/`HEURISTIC`) and a precise source location, so you can tell a compiler-grade fact from an inferred guess.

Source files are always the source of truth; everything RAGpilot stores is derived, rebuildable state (`ragpilot rebuild` proves it).

## Installation

Requires **Python 3.12+** already on your `PATH` — RAGpilot isn't published on PyPI yet, and these scripts don't install Python itself.

### Install the CLI

One command finds your Python, creates an isolated virtual environment, and installs `ragpilot`:

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/gzarog/Ragpilotv2/main/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/gzarog/Ragpilotv2/main/install.ps1 | iex
```

It installs into `~/.ragpilot` (`%LOCALAPPDATA%\RAGpilot` on Windows) and links `ragpilot` onto a per-user bin directory. If that directory isn't already on your `PATH`, the script prints the one-line fix (on Windows it adds it to your user `PATH` automatically — open a new terminal afterward).

Verify it:

```bash
ragpilot version
ragpilot doctor
```

### Install from source

For development, or to track an unreleased change:

```bash
git clone https://github.com/gzarog/Ragpilotv2.git
cd Ragpilotv2
pip install -e .
```

For running the test suite and linting, install the `dev` extra instead:

```bash
pip install -e ".[dev]"
```

No system dependencies are required beyond Python 3.12+. On first use of a document source or semantic search, RAGpilot downloads and locally caches small ML models (Docling's layout model for PDFs, a sentence-embedding model) — after that, everything runs offline.

## Quick start

```bash
ragpilot init                                    # create ~/.ragpilot (or %LOCALAPPDATA%\RAGpilot on Windows)
ragpilot source add /path/to/a/repo/or/docs       # register a folder to index
ragpilot index                                    # parse code + documents, build the knowledge graph
ragpilot status --json                            # what got indexed
ragpilot doctor                                   # health check

ragpilot search "SettlementService"                # lexical search across code + docs
ragpilot symbol SettlementService                  # look up a symbol
ragpilot callers SettlementService                  # who calls it
ragpilot impact SettlementService                   # blast-radius analysis: callers, docs, tests
ragpilot explore "what breaks if SettlementService changes?"   # the primary retrieval command

ragpilot serve --mcp                              # expose everything above to an MCP-speaking agent
ragpilot watch                                     # keep indexing as files change (foreground)
ragpilot backup                                    # snapshot the knowledge base
```

## Features

### Code intelligence
Tree-sitter-based parsing extracts classes, interfaces, structs, enums, functions, methods, properties, fields, imports, inheritance, and calls into a normalized entity/relationship graph, queryable via `ragpilot symbol|callers|callees|references`. Fully supported languages: **Python, JavaScript, TypeScript/TSX, Go, Java, Rust, C#**. A recognized file in an unsupported language still indexes (just without extracted entities); a file that fails to parse is isolated and recorded as failed without stopping the rest of the run.

### Document ingestion
A [Docling](https://github.com/docling-project/docling)-backed pipeline converts **PDF, DOCX, PPTX, XLSX, HTML, Markdown, TXT, and EML** files into a normalized heading/paragraph/table structure with page and heading-path provenance on every unit, exposed via `ragpilot docs`. PDFs are internally converted to Markdown, cached by content hash, and reparsed from that Markdown -- so re-indexing an unchanged PDF skips Docling's expensive layout/table-structure model entirely. A corrupt or unsupported document is isolated and recorded as failed rather than aborting the run.

### Cross-domain linking
After indexing, RAGpilot connects code entities to the documents that describe them — matching on exact/qualified identifiers, filenames, and HTTP route mentions, each scored on the same confidence ladder as the code graph. `ragpilot link add|remove|list` lets you inspect the link graph and pin or remove a mapping by hand; automated linking never overrides an explicit one.

### Search & retrieval
- `ragpilot search QUERY` — ranked lexical search merging exact/qualified-symbol matches, full-text hits, and document title/heading matches.
- `ragpilot explore "QUERY"` — the primary retrieval command: a deterministic query planner picks the right strategies (symbol lookup, graph traversal, full-text, document links) for the question and assembles a budgeted, deduplicated evidence package.
- `ragpilot impact SYMBOL` — a symbol's defining location, callers/callees, linked documents, a naming-convention "tests" heuristic, and a LOW/MEDIUM/HIGH blast-radius bucket.

### MCP server (agent integration)
`ragpilot serve --mcp` starts a stdio MCP server exposing `ragpilot_explore`, `ragpilot_search`, `ragpilot_symbol`, `ragpilot_callers`, `ragpilot_callees`, `ragpilot_impact`, `ragpilot_documents`, `ragpilot_status`, and `ragpilot_ask` — each a thin wrapper over the same functions backing the CLI, so an agent sees exactly what you'd see at the terminal. Responses are versioned, bounded in size, and every call has a configurable timeout. `ragpilot install-agent [--write PATH]` prints the config snippet needed to register RAGpilot with a client like Claude Code — it only prints/writes, it never edits a client's config file on its own.

### Continuous indexing
`ragpilot watch` (foreground) or `ragpilot daemon start|stop|restart|status` (background) watches every enabled source — local roots via native OS filesystem events, network/UNC roots by polling — and keeps the knowledge base current, plus a periodic full reconciliation as a safety net. A source that goes temporarily unreachable (an unmounted network share, a disconnected drive) is flagged `offline` rather than having its knowledge mistakenly deleted, and reconciles for real once it's back.

### Operations
- `ragpilot backup [PATH]` — an online, consistent snapshot (SQLite's backup API, not a raw file copy) of the knowledge base into one archive. Never includes your original source files.
- `ragpilot restore ARCHIVE` — verifies and integrity-checks a backup before atomically swapping it into place; a bad archive is refused before anything live is touched.
- `ragpilot rebuild [--source ID]` — wipes and re-indexes a source from scratch, proving source files are the real truth.
- `ragpilot upgrade` — applies pending schema migrations, backing up automatically first.

### Optional: semantic search & AI-assisted answers
Everything above works fully offline with no LLM. Two opt-in extras layer on top:
- **Semantic search** (`ragpilot config set search.semantic true`): local sentence embeddings (no network once the model is cached) surface similarity-based results as their own clearly lower-confidence tier, never mixed into exact/graph matches.
- **`ragpilot ask "QUESTION"`**: runs the same deterministic retrieval as `explore`, then hands the question and that evidence to a configured LLM provider (OpenAI, Anthropic, Ollama, or any OpenAI-compatible endpoint) for a synthesized, evidence-grounded answer. Cloud providers require explicitly opting in (`privacy.external_ai_allowed: true`); a local Ollama endpoint is exempt only when it actually resolves to loopback.

## Configuration

Settings live in `<runtime dir>/config.yaml` (`~/.ragpilot` on Linux/macOS, `%LOCALAPPDATA%\RAGpilot` on Windows) and can be read/written via `ragpilot config get|set`, e.g.:

```bash
ragpilot config set search.semantic true
ragpilot config set ai.provider ollama
ragpilot config set ai.model llama3.2
```

By default: no data leaves your machine, no telemetry is sent, and no external AI provider is called.

## Design principles

- **Local-first**: source material and derived knowledge stay on disk by default.
- **AI-optional**: search, graph traversal, and impact analysis work without any LLM or network access; semantic search and `ragpilot ask` are opt-in additions layered on top, never required.
- **Source of truth**: source files are authoritative; the RAGpilot database is rebuildable derived state.
- **Evidence-first**: every result traces back to a file, line/page, and section.
- **Fault isolation**: one malformed file must never stop the indexer or crash the daemon.

## Implementation history

RAGpilot was built out in nine sequential, independently mergeable phases, each landed as its own pull request:

1. Production Foundation — CLI, configuration, source registry, SQLite storage, durable job queue, logging, health/doctor
2. Code Intelligence — Tree-sitter parsing, symbol/reference extraction, code graph, FTS5
3. Docling Document Pipeline — document ingestion, normalization, provenance, failure isolation
4. Unified Knowledge Model — entity normalization, cross-domain (code ↔ docs) linking, confidence/evidence model
5. Retrieval — search, callers/callees, references, impact analysis, explore, query planner, context builder
6. MCP Server — stdio MCP server and agent-facing tools
7. Incremental Runtime — daemon, file watchers, polling, reconciliation, crash recovery, offline-source safety
8. Operations — backup/restore, upgrade, rebuild, metrics, packaging/release integrity
9. Optional Intelligence — local embeddings, semantic search, LLM provider abstraction, `ragpilot ask`

See `CHANGELOG.md` for what shipped in each phase in detail, `CONTRIBUTING.md` for development setup, and `SECURITY.md` for the security policy.
