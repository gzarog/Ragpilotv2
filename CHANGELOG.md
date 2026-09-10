# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Phase 1: Production Foundation.
  - `ragpilot` CLI (Typer) with `init`, `source add|list|info|enable|disable|remove`,
    `index`, `status`, `doctor`, `health`, `config show|get|set`, and `version`.
  - Layered Pydantic v2 configuration (defaults < user config < project config
    < environment variables < CLI overrides).
  - Platform-aware runtime directory layout (`~/.ragpilot`, `%LOCALAPPDATA%\RAGpilot`),
    overridable via `RAGPILOT_HOME`.
  - Source registry with local/network detection, and file discovery with
    `.gitignore`/`.ragpilotignore` support, default excludes, and secret-filename
    exclusion.
  - Content hashing with mtime+size fast-skip for incremental indexing.
  - SQLite storage (WAL, foreign keys, busy timeout) with an explicit,
    idempotent migration system.
  - Durable job queue with exponential backoff and crash recovery
    (`PROCESSING` jobs are requeued on startup).
  - A pluggable file-kind processor registry (extension point for later
    phases' code/document parsers), shipping a default "raw" processor for
    Phase 1.
  - Structured JSON logging plus a Rich console renderer.
  - `PathGuard` to confine all filesystem access to registered source roots.
  - Stable CLI exit codes (0-8) mapped from a typed exception hierarchy.
  - Unit and integration test suite, plus a GitHub Actions CI workflow
    (Linux/macOS/Windows x Python 3.12).

- Phase 2: Code Intelligence.
  - Tree-sitter parsing via `tree-sitter` + `tree-sitter-language-pack`
    (prebuilt grammar wheels for every target platform, no source
    compilation) -- see "Language coverage" below for what is fully wired
    up vs. deferred.
  - `code/parser.py` (language detection + parsing), `code/extractor.py`
    (a single, language-agnostic engine driven entirely by per-language
    Tree-sitter `.scm` query files under `code/queries/`), `code/resolver.py`
    (best-effort call/inheritance/import resolution with a documented
    EXACT/HIGH/MEDIUM confidence ladder), and `code/framework_rules.py`
    (two narrow, HEURISTIC-only examples: Flask/FastAPI-style Python route
    decorators, ASP.NET-style C# `[Route]`/`[Http*]` attributes).
  - Normalized entity types (`Namespace/Class/Interface/Struct/Enum/
    Function/Method/Property/Field`) and relationship types (`CALLS/
    IMPLEMENTS/EXTENDS/IMPORTS/REFERENCES/CONTAINS/DEFINED_IN`) added to
    `core/models.py`, reusing Phase 1's model system.
  - A new, additive `entities`/`relationships`/`code_fts` (FTS5) schema
    migration (`storage/schema.py` `KNOWLEDGE_DB_V2`) and matching
    repositories (`entities_repo.py`, `relationships_repo.py`). Indexing a
    file's entities is atomic (delete previous generation, insert new,
    update FTS, all in one transaction), mirroring Phase 1's generational
    file-indexing pattern.
  - `CodeProcessor` registered against `FileKind.CODE` in the existing
    `ProcessorRegistry` (`indexing/coordinator.py`'s `ProcessorContext` grew
    a few coordinator-provided fields -- connection, file id, source root,
    next generation -- for this; its scan/enqueue/claim/retry loop is
    unchanged). A syntax error or a raised parser exception is isolated to
    that one file via the existing `index_errors`/retry machinery, exactly
    like Phase 1's "poisoned file" handling.
  - Read-only CLI commands `ragpilot symbol|callers|callees|references`,
    all `--json`-capable with the Phase 1 envelope, backed by a shared,
    depth- and result-capped graph traversal (`code/graph.py`) that Phase
    5's `impact` command is expected to reuse.
  - Parser golden tests per language, resolver confidence-ladder unit
    tests, framework-heuristic unit tests, a direct `code_fts` unit test,
    and an end-to-end CLI integration test (multi-file/multi-language
    project, broken-file isolation, a simulated Tree-sitter parse
    exception, and `--json` output) under `tests/fixtures/languages/`.

  **Language coverage**: Python, JavaScript, TypeScript/TSX, Go, Java,
  Rust and C# are all fully implemented end-to-end (extraction +
  resolution + golden tests) -- all seven of the blueprint's priority
  languages installed and parsed cleanly in this environment, so none were
  dropped. C#'s `base_list` does not distinguish a base class from
  implemented interfaces at the grammar level; every entry is
  conservatively tagged `EXTENDS` rather than guessing from naming
  conventions (documented in `code/queries/csharp.scm`). Any other
  extension `sources/detector.py` already classifies as code (e.g. `.rb`,
  `.sql`, `.sh`, `.php`, `.kt`) has no grammar wired up yet and is
  recorded indexed without extracted entities rather than failing.

- Phase 3: Docling Document Pipeline.
  - `documents/docling_adapter.py` (a thin wrapper around Docling's Python
    `DocumentConverter`), `documents/normalizer.py` (turns a
    `DoclingDocument` into a flat, index-addressed unit list with
    heading-path/page provenance on every unit), `documents/chunker.py`
    (groups that into size-bounded, still-provenance-carrying chunks),
    `documents/metadata.py` (document-level metadata -- whatever Docling
    exposes), and `documents/pipeline.py` (`document_processor`, wiring
    all four into storage).
  - **Supported formats**: PDF, DOCX, PPTX, XLSX, HTML, Markdown, TXT,
    EML. Any other extension `sources/detector.py` still classifies as
    `FileKind.DOCUMENT` (legacy `.doc`/`.ppt`/`.xls`, OpenDocument, `.rtf`,
    `.csv`, `.rst`) is recorded indexed without derived document content,
    mirroring Phase 2's "recognized extension, not wired up yet"
    fallback. OCR, images, audio/video, and VLM pipelines are explicitly
    out of scope for this phase (`documents.ocr` in `core/config.py` is
    read by nothing yet).
  - Normalized entity types `Document`, `Section`, `Paragraph`, `Table`
    added to `core/models.py`, plus `DocumentFormat`/`SectionKind` enums,
    reusing Phase 1/2's plain-Pydantic model conventions. Every row
    carries its heading path, page range, and a content hash where
    applicable -- documents don't need Phase 2's full
    entity/relationship/confidence machinery (no cross-document
    references exist yet), so hierarchy is stored directly via
    `parent_id` + a redundant `heading_path` rather than `CONTAINS`
    relationship rows.
  - A new, additive `documents`/`document_sections`/`document_fts` (FTS5)
    schema migration (`storage/schema.py` `KNOWLEDGE_DB_V3`) and a
    matching repository (`documents_repo.py`). Indexing a file's document
    content is atomic (delete previous generation, insert new, update
    FTS, all in one transaction), exactly like Phase 1/2's generational
    pattern.
  - `document_processor` registered against `FileKind.DOCUMENT` in the
    existing `ProcessorRegistry` (gated on `documents.enabled`). A
    corrupt/unreadable/unsupported-format document is caught and recorded
    via `index_errors` without crashing the coordinator or the rest of
    the run, exactly like Phase 1/2's file-level fault isolation. A PDF
    over `documents.max_pages` is marked `SKIPPED_LIMIT` (the same status
    Phase 1 uses for oversized files) -- checked via `pypdfium2`'s page
    count alone, before Docling's own conversion would ever run, so an
    oversized PDF never triggers a model download.
  - Fixed a latent bug `files_repo.delete` had carried since Phase 1: it
    never cascaded to Phase 2/3's derived-content tables
    (`entities`/`relationships`/`documents`/`document_sections`), so
    reconciling a deleted source file that already had derived content
    raised a foreign-key `IntegrityError` instead of deleting cleanly.
  - Read-only `ragpilot docs [--source ID] [--json]`, following Phase
    1/2's `--json` envelope and exit-code conventions.
  - **The `docling_pdf` test tradeoff**: Docling's PDF pipeline downloads
    layout/table-structure model weights from Hugging Face on first use.
    Every other supported format is converted by Docling's rule-based
    backends and is exercised by the default test suite with real
    fixtures (`tests/fixtures/documents/`, three of them --
    `document.docx`/`presentation.pptx`/`spreadsheet.xlsx` -- generated by
    a small dev-only script, `python-docx`/`python-pptx`/`openpyxl`
    declared as dev/test-only dependencies). PDF conversion tests are
    marked `@pytest.mark.docling_pdf` and excluded from the default
    `pytest -q` run (`pyproject.toml`'s `addopts`); run them explicitly
    with `pytest -m docling_pdf` (see CONTRIBUTING.md). CI runs them too,
    in a separate, non-blocking job.
  - **Deferred, out of scope for this phase**: OCR, images, audio/video,
    OpenDocument, EPUB, advanced VLM pipelines, cross-domain (code <->
    document) linking, `ragpilot search`/`explore`, and any daemon/watcher
    integration.

- Phase 4: Unified Knowledge Model.
  - `knowledge/linker.py`: a cross-domain linker connecting code entities to
    the documents that describe them (blueprint section 19). Implements the
    blueprint's priority list to the extent Phases 1-3 actually give it
    signal to work with: exact bare-identifier matching, qualified
    (fully-dotted) identifier matching (scored at least as strong as bare
    matching, per the blueprint), filename matching, a modest class-only
    alias of a qualified name, and route/method matching that reuses Phase
    2's existing `framework_rules.py`-tagged HTTP endpoint findings rather
    than building any new route/message-broker infrastructure. Explicit,
    user-defined mappings (`ragpilot link add`) are the highest-trust
    source and are never written, overridden, or contradicted by the
    automated linker (different `resolver` values, proven by a dedicated
    test). Semantic/embedding-based linking is explicitly out of scope
    here, per the blueprint ("semantic similarity may suggest links but
    must not silently create high-confidence facts") -- Phase 4 has no
    embedding infrastructure to do so anyway (that's Phase 9).
  - Confidence ladder (`knowledge/confidence.py`, re-exporting Phase 2's
    `Confidence` enum rather than duplicating it): explicit user mappings =
    EXACT; exact/qualified identifier matches = HIGH; filename/alias
    matches = MEDIUM; route-heuristic matches = HEURISTIC -- the same
    tiers Phase 2's `code/resolver.py` already established, documented in
    the same comment style.
  - `knowledge/entities.py`: a thin query facade unifying "look up an
    entity by id or canonical/qualified name" across code entities and
    documents, wrapping `entities_repo`/`documents_repo`/`files_repo`
    rather than adding a new persistence layer.
  - `knowledge/evidence.py`: normalizes a code relationship or a
    cross-domain link into the blueprint's evidence contract (section 57)
    -- `{source, path, location: {line_start, line_end, page, section},
    entity, relationship, confidence}` -- computed at read time from
    existing Phase 2/3 storage rather than materializing a separate
    `evidence` table (see "Storage design" below).
  - Storage: a new additive migration (`storage/schema.py`
    `KNOWLEDGE_DB_V4`, `cross_links` table) rather than reusing Phase 2's
    `relationships` table directly -- `relationships.target_entity_id` is
    a foreign key into `entities(id)` only, and a document is not an
    entity row, so a document-side link needs its own table
    (`entity_id`/`document_id`/optional `section_id`, `resolver`,
    `confidence`, `evidence`). No separate `evidence` table: evidence is
    derived at read time (`knowledge/evidence.py`) from
    `entities`/`relationships`/`documents`/`document_sections`/
    `cross_links`, which is simpler and has no known performance need yet
    to justify materializing it.
  - The cross-domain linking pass runs as part of `ragpilot index`
    (`cli/index.py`), after each source's per-file processor queue has
    fully drained -- a link needs both a code entity and a document to
    exist, so it cannot be computed per-file the way Phase 2/3's atomic
    generational writes are. It is incremental: only entities/documents
    belonging to files (re)indexed *this run* are matched, searched
    against the full existing project corpus in both directions (a new
    document against all existing code, and vice versa) -- a full-corpus
    recompute on every run does not scale. Stale links are cleaned up via
    the same generational-deletion pattern Phase 1-3 already use:
    `entities_repo.delete_by_file`/`documents_repo.delete_by_file` (and
    `files_repo.delete`) now cascade into the new `links_repo`, so a link
    pinned to a file's previous generation (including an explicit,
    user-defined one) is removed when that file is re-indexed with
    different content or deleted -- see `links_repo.py`'s docstrings for
    why that is unavoidable given Phase 2 entities have no identity stable
    across a content-changing regeneration.
  - Read/write CLI `ragpilot link add ENTITY DOCUMENT [--section ID]`,
    `ragpilot link remove ID`, `ragpilot link list [--entity NAME]
    [--document ID] [--json]`, following Phase 1-3's `--json` envelope and
    exit-code conventions. Deliberately minimal (per the blueprint, full
    `explore`/`impact` presentation is Phase 5's job): enough to inspect
    the link graph and manually correct it.
  - **Known limitations**: matching is exact/substring-based (with word-
    boundary checks) over `document_sections` text -- no fuzzy or semantic
    matching, and a common short identifier can produce a noisy bare-name
    match (no suppression heuristic beyond boundary-checking is applied).
    An explicit link pinned to a code entity only survives re-indexing
    while that entity's *file* is unchanged (classified `UNCHANGED` and
    never reprocessed) -- Phase 2 entity ids are not stable across a
    content-changing regeneration of their file, so a link pinned to one
    is cleaned up along with it, the same as an auto-discovered link
    would be. Cross-domain linking is scoped to one project (one
    source's `knowledge.db`) at a time; it does not link across two
    different registered sources.

- Phase 5: Retrieval.
  - `retrieval/planner.py`: a small, deterministic (no LLM) query
    classifier -- a bare identifier routes to identifier+FTS, "who calls
    X"/"callers of X" routes to symbol lookup + incoming `CALLS` graph
    traversal, "documents about X" routes to FTS (+ semantic once
    `search.semantic` is enabled), and "what breaks if X changes"/"impact
    of X" routes to symbol + callers + callees + tests + docs -- matching
    the blueprint's own four illustrative examples (section 25). A small,
    ordered set of regex rules, not an NLP query-understanding system, per
    the blueprint's "initially deterministic" scope.
  - `retrieval/lexical.py` and `ragpilot search QUERY [--limit N]
    [--json]`: merges exact/qualified-identifier matches, `code_fts`/
    `document_fts` hits, file-path substring matches, and document
    title/heading matches into one ranked list. Ranking order: exact
    symbol > qualified symbol > title/heading > FTS rank > path relevance,
    with entity kind, file recency (mtime), and source id as deterministic
    tie-breakers within a tier (there is no stored per-entity-kind
    usage-frequency or source-priority signal in Phases 1-4 to rank
    *across* tiers on, so those three fold in as tie-breakers instead of
    being invented as new top-level signals).
  - `retrieval/graph.py`: composes Phase 2's existing `code/graph.py` BFS
    (`traverse`/`traverse_symbol`/`find_symbol_matches`) rather than
    reimplementing graph walking. `cli/references.py`'s incoming+outgoing
    CALLS/IMPORTS/REFERENCES aggregation was extracted here (behavior-
    preserving refactor, same output) so `impact`/`explore` reuse it too.
    Also adds edge *resolution* (`resolved_incoming`/`resolved_outgoing`,
    pairing each traversal edge with its neighboring `Entity`/file) and
    `is_test_file`/`find_tests_referencing`: a small, documented,
    naming-convention filter (`test_*.py`, `*_test.py`/`.go`,
    `*Test(s).cs`/`.java`, `*.test.ts(x)`/`*.spec.ts(x)`, etc.) over
    Phase 2's already-stored CALLS/IMPORTS/REFERENCES edges -- not a new
    test-framework-detection subsystem, and its result's provenance is a
    filename guess, independent of each edge's own `Confidence`.
  - `cli/impact.py` and `ragpilot impact SYMBOL [--max-depth N] [--limit
    N] [--json]`: defining location(s), callers/callees (Phase 2's CALLS
    graph -- the blueprint's "Produced by"/"Consumed by" vocabulary maps
    onto `PRODUCES`/`CONSUMES` relationship types Phases 1-4 never
    populate, see `core/models.py`), the tests heuristic above,
    cross-domain document links (Phase 4's `links_repo`, shaped through
    `knowledge/evidence.py`), a combined code/document confidence summary,
    and a "blast radius" bucket. Blast radius is a deliberately simple,
    documented heuristic -- `LOW` (score 0-2), `MEDIUM` (3-7), `HIGH`
    (8+) -- over one count (distinct callers + distinct linked documents
    touched), not a calibrated model.
  - `retrieval/context_builder.py`: the blueprint's evidence-package
    assembly (section 27) -- dedupes same-file/location evidence (keeping
    the higher-confidence one), prioritizes exact evidence over heuristic,
    and enforces a new `context:` config budget (`max_chars`, `max_files`,
    `max_graph_nodes`, defaults 30000/20/100) with explicit, reported
    truncation rather than a silent drop. Graph relationships are carried
    as `A -[REL]-> B` paths, not just bare endpoints. A pure function with
    no database access of its own, built on `knowledge/evidence.py`'s
    existing evidence shape.
  - `cli/explore.py` and `ragpilot explore "QUERY" [--json]`: the primary
    retrieval command (blueprint section 25) -- runs the planner's chosen
    strategies and returns Summary/Relevant symbols/Relevant paths/Call
    flows/Dependencies/Documents/Tests/Requirements/Incidents/Evidence.
    Summary is a short, deterministically-templated string, never an LLM
    summary (no LLM is used anywhere in this phase). "Requirements" and
    "Incidents" are document *categories* the blueprint lists as example
    entity types (section 17) that Phases 1-4 never classify a document
    into, so those two sections always come back empty rather than this
    phase inventing a document classifier to fill them.
  - `retrieval/semantic.py`: the seam for Phase 9's real semantic/vector
    search -- returns a clearly-marked skipped result while
    `search.semantic` is `false` (the default) and raises a specific,
    typed `SemanticSearchNotImplementedError` if ever invoked while
    enabled, so `planner.py` (and later Phase 6's MCP tools) have one
    stable place to plug it in without this phase faking a result.
  - Unit tests for the planner's classification rules (each blueprint
    example plus supporting cases), lexical ranking (fixtures isolating
    exact/qualified/FTS/path/title signals), the context builder's
    dedup and all three budget knobs independently, the tests-heuristic
    filename patterns, and blast-radius bucket boundaries; an end-to-end
    integration test indexing a mixed code+document project with a
    cross-domain link and exercising `search`/`impact`/`explore`
    (including `--json`) through the real CLI.

- Phase 6: MCP Server.
  - `mcp/server.py` and `mcp/tools.py`: a stdio MCP server (blueprint:
    "MCP over stdio as the default agent transport, no external listening
    port") built on the official `mcp` SDK's high-level
    `mcp.server.fastmcp.FastMCP` decorator/registry API (pinned `mcp>=1.2,
    <2` -- the SDK's 2.x line renames `FastMCP` to `MCPServer` and
    reshuffles its API; 1.x's `FastMCP` is the well-established, directly
    testable one), exposing 8 tools: `ragpilot_explore` (primary),
    `ragpilot_search`, `ragpilot_symbol`, `ragpilot_callers`,
    `ragpilot_callees`, `ragpilot_impact`, `ragpilot_documents`,
    `ragpilot_status`. Each tool is a thin adapter over the exact same
    functions the equivalent CLI command calls (`code/graph.py`,
    `retrieval/lexical.py`, `retrieval/planner.py`, and newly-extracted
    `_run` helpers in `cli/docs.py`/`cli/status.py`/`cli/impact.py`
    mirroring `cli/explore.py`'s existing split) -- no retrieval logic is
    reimplemented, and every tool call bootstraps the same `AppContext`
    (same `RAGPILOT_HOME`/config resolution) a CLI invocation would, so an
    agent sees exactly what `ragpilot explore`/`search`/... would show.
  - `mcp/schemas.py`: one explicit, versioned Pydantic output model per
    tool (`schema_version`/`ok`/`error` on every response, mirroring the
    CLI's own `--json` envelope convention) instead of an ad hoc dict, so
    FastMCP derives deterministic JSON Schema straight from the typed
    signatures/models.
  - Bounded responses: `ragpilot_explore` routes through Phase 5's
    `retrieval/context_builder.py` budget (`context.max_chars`/
    `max_files`/`max_graph_nodes`), overridable per call via optional
    tool arguments.
  - Clear errors: a new `mcp/tools.py`-internal mapping turns any
    `RagpilotError` into a typed `{"type": "UsageError", "message": ...}`
    -shaped result (by exception class name) rather than a raw traceback
    or protocol-level failure -- "no such source", an empty query, an
    unresolvable symbol, etc. all come back as a normal, `ok=false` tool
    result a client can branch on.
  - Timeout enforcement: a new `mcp.request_timeout_seconds` config field
    (default 30s) bounds every tool call via `asyncio.wait_for` around an
    `asyncio.to_thread`-run synchronous call. Documented as an honest
    wall-clock "stop waiting", not true cancellation: Python cannot force-
    kill a running thread, so a timed-out call's thread runs to
    completion and cleans itself up in the background rather than
    blocking the client any further.
  - stdout/stderr discipline: every MCP-tool-call `AppContext` is
    bootstrapped with `log_console_format="json"` so WARNING+ console
    logs go to stderr (plain `logging.StreamHandler`) instead of the
    CLI's interactive, stdout-default `RichHandler` -- stdout is the MCP
    stdio transport's JSON-RPC framing channel, and a stray log line on
    it would corrupt the protocol stream.
  - `ragpilot serve --mcp`: starts the blocking stdio server loop after
    checking `mcp.enabled` (fails fast with `ConfigError`/exit code 3 if
    disabled, never silently starting anyway) -- `--mcp` is required
    since it is the only transport this phase implements (the optional
    REST API is Phase 8). Server *construction* (`mcp/server.py`'s
    `build_server`) is pure and unit-tested directly; the blocking stdio
    loop itself is not exercised in the test suite.
  - `ragpilot install-agent [--write PATH]`: prints the standard
    `{"mcpServers": {"ragpilot": {"command": "ragpilot", "args": ["serve",
    "--mcp"]}}}` JSON snippet most MCP clients expect, and only writes it
    to disk when given an explicit `--write PATH`. Deliberately does not
    discover or edit any real client config file (e.g. `~/.claude.json`)
    on its own -- printing/writing only to a path the user names is the
    safe version of blueprint section 74's "connect AI agent" step.
  - Unit tests calling all 8 tool functions directly (a FastMCP-decorated
    tool is still just its underlying coroutine) against a small indexed
    fixture project, plus a context-budget test, a bad-input/unknown-
    symbol structured-error test, a timeout test (a monkeypatched slow
    retrieval call proves the configured timeout fires rather than
    hanging), `mcp/server.py` construction tests, and CLI tests for
    `serve --mcp`'s `mcp.enabled=false` fast-fail path and
    `install-agent`'s print/`--write` output.
