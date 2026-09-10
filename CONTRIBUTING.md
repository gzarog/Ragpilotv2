# Contributing to RAGpilot

## Development setup

RAGpilot targets Python 3.12+.

```bash
python3.12 -m venv .venv
source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

This installs the package in editable mode plus the dev toolchain
(`pytest`, `ruff`, `mypy`).

## Running the checks

```bash
pytest -q                 # tests
ruff check .               # lint
mypy src/ragpilot           # type-check
```

All three must pass before opening a pull request; CI runs the same checks
across Linux, macOS, and Windows.

### The `docling_pdf` marker

Docling's PDF pipeline (layout detection, table structure) downloads model
weights from Hugging Face on first use. That is a real network dependency,
so tests that actually invoke it are marked `@pytest.mark.docling_pdf` and
excluded from the default run (`pyproject.toml`'s `addopts` runs
`-m 'not docling_pdf'`). Run them explicitly:

```bash
pytest -m docling_pdf -q
```

Every other Phase 3 format (DOCX, PPTX, XLSX, HTML, Markdown, TXT, EML) is
converted by Docling's rule-based backends and never touches that
download path, so those tests run in the default suite like everything
else. CI runs `docling_pdf` tests too, but in a separate,
non-blocking (`continue-on-error`) job -- see `.github/workflows/ci.yml`.

## Test isolation

Every test must isolate RAGpilot's runtime directory via the `RAGPILOT_HOME`
environment variable (see the `ragpilot_home` fixture in `tests/conftest.py`)
and a `tmp_path`-based current working directory where project config or
source files are involved. Tests must never read or write the real
`~/.ragpilot` directory.

## Project layout

- `src/ragpilot/cli/` — Typer CLI commands
- `src/ragpilot/core/` — config, paths, models, errors, app lifecycle
- `src/ragpilot/sources/` — source registry, scanning, ignore rules, hashing
- `src/ragpilot/storage/` — SQLite connection handling, schema, migrations, repositories
- `src/ragpilot/indexing/` — scan/classify/enqueue/process orchestration
- `src/ragpilot/code/` — Tree-sitter parsing, extraction, resolution, framework heuristics
- `src/ragpilot/documents/` — Docling adapter, normalization, chunking, metadata
- `src/ragpilot/telemetry/` — structured logging
- `src/ragpilot/security/` — path containment and secret-file exclusion

This repository is built out in sequential phases (see `README.md`); please
keep changes scoped to the phase you are working on rather than adding
speculative structure for later phases.

## Document fixtures

`tests/fixtures/documents/` holds committed, hand-verified fixtures for
Phase 3's golden tests (`simple.txt`, `simple.md`, `simple.html`,
`sample.eml`, `corrupt.docx`, `sample.pdf` by hand; `document.docx`,
`presentation.pptx`, `spreadsheet.xlsx` generated). Regenerate the latter
with:

```bash
python tests/fixtures/documents/generate_fixtures.py
```

## Commit style

Keep commits focused and describe the "why" as well as the "what". Update
`CHANGELOG.md` under "Unreleased" for user-visible changes.
