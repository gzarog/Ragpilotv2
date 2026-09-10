"""Shared, schema-level data models used across the indexing pipeline.

These are plain Pydantic models (not an ORM) that mirror the SQLite row
shapes defined in ``storage.schema``. Repositories translate between rows
and these models.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class SourceType(StrEnum):
    LOCAL = "local"
    NETWORK = "network"


class IndexingMode(StrEnum):
    FULL = "full"


class FileKind(StrEnum):
    CODE = "code"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class FileStatus(StrEnum):
    DISCOVERED = "discovered"
    CLASSIFIED = "classified"
    QUEUED = "queued"
    PROCESSING = "processing"
    RETRY = "retry"
    FAILED = "failed"
    INDEXED = "indexed"
    SKIPPED_LIMIT = "skipped_limit"


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    RETRY = "retry"
    FAILED = "failed"
    COMPLETED = "completed"


class JobType(StrEnum):
    INDEX_FILE = "index_file"


class Source(BaseModel):
    model_config = ConfigDict(frozen=False)

    id: str
    path: str
    source_type: SourceType
    enabled: bool = True
    indexing_mode: IndexingMode = IndexingMode.FULL
    include_patterns: list[str] = []
    exclude_patterns: list[str] = []
    last_scan_at: str | None = None
    last_error: str | None = None
    fingerprint: str | None = None
    created_at: str
    updated_at: str


class FileRecord(BaseModel):
    id: str
    source_id: str
    path: str
    kind: FileKind
    size: int
    mtime: float
    content_hash: str | None = None
    status: FileStatus
    generation: int = 0
    parser_version: str = "1"
    last_indexed_at: str | None = None
    last_error: str | None = None
    created_at: str
    updated_at: str


class IndexJob(BaseModel):
    id: str
    source_id: str
    file_id: str
    job_type: JobType
    status: JobStatus
    priority: int = 0
    attempt_count: int = 0
    next_attempt_at: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class IndexErrorRecord(BaseModel):
    id: str
    source_id: str
    file_id: str | None = None
    path: str | None = None
    error_code: str
    error_message: str
    occurred_at: str


class ScannedFile(BaseModel):
    """A file found on disk during a scan, before it has a DB identity."""

    path: str
    size: int
    mtime: float
