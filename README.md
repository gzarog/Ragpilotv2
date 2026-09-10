# RAGpilot

RAGpilot is a local-first knowledge compiler and retrieval engine for software repositories and organizational documents. It has no web UI: it is consumed via a CLI and an MCP server. A local REST API is reserved in configuration (`api:`, disabled by default) but not implemented by any phase below -- consuming RAGpilot programmatically today means the CLI's `--json` output or the MCP server, not HTTP.

This repository was built out in sequential, independently mergeable phases, each landed as its own pull request against `main`:

1. Production Foundation — CLI, configuration, source registry, SQLite storage, durable job queue, logging, health/doctor
2. Code Intelligence — Tree-sitter parsing, symbol/reference extraction, code graph, FTS5
3. Docling Document Pipeline — document ingestion, normalization, provenance, failure isolation
4. Unified Knowledge Model — entity normalization, cross-domain (code <-> docs) linking, confidence/evidence model
5. Retrieval — search, callers/callees, references, impact analysis, explore, query planner, context builder
6. MCP Server — stdio MCP server and agent-facing tools
7. Incremental Runtime — daemon, file watchers, polling, reconciliation, crash recovery
8. Operations — backup/restore, upgrade/rollback, metrics, packaging, release integrity
9. Optional Intelligence — local embeddings, vector retrieval, LLM provider abstraction, `ragpilot ask`

All 9 phases of the blueprint have landed on `main`.

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
ragpilot link list --json
ragpilot link add MyClass.my_method path/to/document.md
ragpilot search "MyClass"
ragpilot impact MyClass
ragpilot explore "what breaks if MyClass changes?"
ragpilot install-agent --write ~/.config/some-mcp-client/ragpilot.json
ragpilot serve --mcp
ragpilot watch
ragpilot daemon start
ragpilot daemon status --json
ragpilot daemon stop
ragpilot backup
ragpilot upgrade
ragpilot rebuild --source SOURCE_ID
ragpilot restore ~/.ragpilot/backups/ragpilot-backup-<timestamp>.tar.gz
ragpilot config set search.semantic true
ragpilot index
ragpilot config set ai.provider ollama
ragpilot config set ai.model llama3.2
ragpilot ask "what does MyClass do?"
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

Phase 3 adds a Docling-backed document pipeline: `ragpilot index` now also
converts document-kind files -- **PDF, DOCX, PPTX, XLSX, HTML, Markdown,
TXT, EML** -- into a normalized heading/paragraph/table structure with page
and heading-path provenance on every unit, stored alongside an FTS5 index
over headings/body text/title, and exposed read-only via `ragpilot docs`.
OCR, images, audio/video, OpenDocument, EPUB, and VLM pipelines are out of
scope for this phase. A corrupt or unsupported document is isolated and
recorded as failed (or, for an extension Phase 3 doesn't convert yet,
indexed without derived content) rather than aborting the run; a PDF over
`documents.max_pages` is marked `skipped_limit`. Docling's PDF pipeline
downloads layout/table-structure model weights on first use -- tests that
exercise it are marked `docling_pdf` and excluded from the default test run
(see CONTRIBUTING.md).

Phase 4 adds the unified knowledge model:
`ragpilot index` now also runs a cross-domain linking pass, after each
source's normal per-file indexing completes, connecting code entities to
the documents that describe them. It matches on exact and fully-qualified
identifiers, source filenames, a modest class-only alias, and (reusing
Phase 2's `framework_rules.py` findings) HTTP route/method mentions --
each tier scored on the same EXACT/HIGH/MEDIUM/HEURISTIC ladder Phase 2's
resolver introduced. The pass is incremental (only files (re)indexed in
that run are matched against the rest of the project) and never overrides
an explicit, user-defined link. `ragpilot link add|remove|list` lets a
person inspect the link graph and pin or remove a mapping by hand; Phase
5's `explore`/`impact` will build its presentation on top of this. Fuzzy/
semantic linking is explicitly out of scope (no embedding infrastructure
exists yet -- that is Phase 9 -- and the blueprint bars semantic
similarity from silently minting high-confidence facts even once it
does). The MCP server did not exist yet at this point -- it is Phase 6, below.

Phase 5 adds retrieval: `ragpilot search QUERY` merges
exact/qualified-identifier matches, `code_fts`/
`document_fts` hits, file-path matches, and document title/heading
matches into one ranked list. `ragpilot impact SYMBOL` reports a symbol's
defining location, callers/callees (Phase 2's CALLS graph), cross-domain
document links (Phase 4), a small naming-convention "tests" heuristic, and
a documented LOW/MEDIUM/HIGH "blast radius" bucket. `ragpilot explore
"QUERY"` is the primary retrieval command: a deterministic (no LLM) query
planner picks which of the above strategies a query needs -- e.g. "who
calls X" routes to graph traversal, "documents about X" routes to FTS --
and assembles the result through a budgeted, deduplicated evidence
package (`context:` config: `max_chars`/`max_files`/`max_graph_nodes`).
Real semantic/vector search stays disabled by default
(`search.semantic: false`); `retrieval/semantic.py` was only the seam at
this point in the blueprint -- Phase 9 (below) implements it for real.

Phase 6 adds the MCP server:
`ragpilot serve --mcp` starts a stdio MCP server (built on the official
`mcp` SDK's `FastMCP`) exposing 8 read-only tools --
`ragpilot_explore` (primary), `ragpilot_search`, `ragpilot_symbol`,
`ragpilot_callers`, `ragpilot_callees`, `ragpilot_impact`,
`ragpilot_documents`, `ragpilot_status` -- each a thin adapter over the
exact same functions its CLI counterpart calls, so an MCP-speaking agent
sees exactly what the CLI shows. Every response is a deterministic,
versioned Pydantic model (`schema_version`/`ok`/`error`); `ragpilot_explore`
is bounded by Phase 5's context budget; every call is wrapped in a
configurable wall-clock timeout (`mcp.request_timeout_seconds`, default
30s); and any `RagpilotError` comes back as a typed, structured error
instead of a raw traceback. `ragpilot install-agent [--write PATH]`
prints the MCP client config snippet needed to register RAGpilot with a
client such as Claude Desktop/Claude Code -- it never discovers or edits
a real client config file on its own, only prints (and, with `--write`,
writes to the exact path given).

Phase 7 adds the incremental runtime:
`ragpilot watch` runs a daemon in the foreground (`ragpilot daemon
start|stop|restart|status [--json]` runs the same loop detached in the
background) that watches every enabled source -- local roots via native
OS filesystem events (`watchdog`, debounced by `indexing.debounce_ms`),
network/UNC roots by polling on an interval
(`indexing.network_poll_seconds`) -- and triggers the exact same per-source
indexing pass `ragpilot index` runs, plus a periodic full reconciliation
(`indexing.reconciliation_interval_seconds`, default 15 minutes) as a
safety net independent of watcher events. Graceful shutdown
(SIGINT/SIGTERM) lets an in-flight pass finish before releasing Phase 1's
`RunLock`, never leaving partial state. This phase also fixes a
correctness gap that predates the daemon: `ragpilot index` alone could
previously misread a source root going offline (an unmounted network
share, a deleted directory) as "every file in it was deleted", because
`os.walk` silently returns nothing for a root it cannot list. A source
root's reachability is now checked explicitly before any deletion is
reconciled; an unreachable source flips to a new `offline` status (surfaced
by `ragpilot source list|info` and, as a WARN rather than a failure, by
`ragpilot doctor`) with every existing file/entity/document left
untouched, and flips back to `active` -- reconciling for real -- the
moment the root is reachable again.

Phase 8 adds operations: `ragpilot
backup [PATH]` takes an online, consistent snapshot (SQLite's own backup
API, not a raw file copy) of `sources.db` and every project's
`knowledge.db` into one `.tar.gz` archive with a manifest -- never the
original source files, which stay the user's own data on disk. `ragpilot
restore ARCHIVE` verifies the archive and its schema versions, stops a
running daemon, extracts and integrity-checks every database in a temp
location, and only then atomically swaps it into place (a corrupted or
incompatible archive is refused before anything live is touched).
`ragpilot rebuild [--source ID]` wipes one or every source's
`knowledge.db` and re-indexes it from scratch through the same pipeline
`ragpilot index` uses -- the blueprint's "source files = truth, RAGpilot
DB = rebuildable derived state" principle, runnable on demand. `ragpilot
upgrade` checks every database for pending schema migrations, takes an
automatic backup only when one is actually pending, applies migrations
through the existing (Phase 1) migration system, and reuses `ragpilot
doctor`'s health check to report the result -- there is no automatic
rollback of an already-applied migration; the pre-upgrade backup is the
documented recovery path. `ragpilot status --json` also reports real
metrics (symbol/relationship/document counts, database size, queue
depth) alongside the existing indexing summary. Packaging/release
integrity is scoped to what this environment can do honestly:
`scripts/generate_release_artifacts.py` and a tag-triggered
`.github/workflows/release.yml` build the sdist/wheel, a checksum file,
and a plain dependency manifest -- clearly labeled **unsigned**, since no
code-signing infrastructure exists here; a standalone multi-platform
executable bundle is out of scope for this phase.

Phase 9 (the blueprint's final phase)
adds optional intelligence, entirely opt-in: `explore`/`search`/`impact`/
etc. behave exactly as before when `search.semantic` is left at its
default `false` and no AI provider is configured. Setting
`search.semantic: true` turns on real local semantic search -- text
embeddings computed locally (`sentence-transformers/all-MiniLM-L6-v2`,
run directly through `transformers`, no network needed once weights are
cached) for touched files during `ragpilot index`, stored in a new,
additive `embeddings` table separate from `entities`/`documents`, and
compared via brute-force cosine similarity (a deliberately portable
choice over a loadable SQLite extension like sqlite-vec, see
`CHANGELOG.md`). `ragpilot search`/`ragpilot explore` then surface
semantic hits as their own distinct, lower-confidence
(`Confidence.HEURISTIC`) tier, never mixed into or upgrading a
lexical/graph match. A new `ragpilot ask "QUESTION" [--json]` command
runs the exact same deterministic retrieval `ragpilot explore` uses, then
hands the question and that evidence to a configured `ai:` provider
(OpenAI, Anthropic, Ollama, or any OpenAI-compatible endpoint) for a
synthesized, evidence-grounded answer. A cloud provider always requires
`privacy.external_ai_allowed: true` (defaults `false`); a local Ollama
endpoint is exempt only when it actually resolves to loopback. `ragpilot
serve --mcp` also exposes a `ragpilot_ask` tool alongside the existing 8
read-only ones.

## Design principles

- **Local-first**: source material and derived knowledge stay on disk by default.
- **AI-optional**: search, graph traversal, and impact analysis work without any LLM or network access; local semantic search and `ragpilot ask` (Phase 9) are opt-in additions layered on top, never required.
- **Source of truth**: source files are authoritative; the RAGpilot database is rebuildable derived state.
- **Evidence-first**: every result traces back to a file, line/page, and section.
- **Fault isolation**: one malformed file must never stop the indexer or crash the daemon.
