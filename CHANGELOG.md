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
