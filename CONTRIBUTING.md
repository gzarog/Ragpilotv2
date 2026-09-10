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
- `src/ragpilot/telemetry/` — structured logging
- `src/ragpilot/security/` — path containment and secret-file exclusion

This repository is built out in sequential phases (see `README.md`); please
keep changes scoped to the phase you are working on rather than adding
speculative structure for later phases.

## Commit style

Keep commits focused and describe the "why" as well as the "what". Update
`CHANGELOG.md` under "Unreleased" for user-visible changes.
