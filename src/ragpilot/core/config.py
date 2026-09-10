"""Layered configuration loading.

Precedence, highest wins: CLI overrides > environment variables
(``RAGPILOT_`` prefix, ``__`` nesting) > project config
(``./.ragpilot.yaml``) > user config (``<runtime_dir>/config.yaml``) >
built-in defaults.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from ragpilot.core import paths
from ragpilot.core.errors import ConfigError

_ENV_PREFIX = "RAGPILOT_"


class RuntimeConfig(BaseModel):
    log_level: str = "info"
    max_workers: int = 6
    max_memory_mb: int = 4096
    temp_directory: str = "auto"


class IndexingConfig(BaseModel):
    watch: bool = True
    debounce_ms: int = 2000
    max_file_size_mb: int = 100
    follow_symlinks: bool = False
    hash_algorithm: str = "sha256"
    # Phase 7: how often a network/UNC source is fingerprinted (mtime+size
    # scan) since native filesystem events don't reliably cross a network
    # mount -- see watcher/network.py.
    network_poll_seconds: int = 30
    # Phase 7: how often the daemon's periodic reconciliation timer does a
    # full rescan+diff pass per source as a safety net independent of
    # watcher events, catching whatever a missed/coalesced OS event or a
    # dropped poll tick missed -- see service/daemon.py.
    reconciliation_interval_seconds: int = 900


class DocumentsConfig(BaseModel):
    enabled: bool = True
    ocr: str = "auto"
    max_pages: int = 1000


class CodeConfig(BaseModel):
    enabled: bool = True


class SearchConfig(BaseModel):
    lexical: bool = True
    graph: bool = True
    semantic: bool = False


class ContextConfig(BaseModel):
    """Phase 5's context-builder budget (blueprint section 27) -- caps how
    much evidence ``retrieval/context_builder.py`` will hand back to a
    caller (``explore`` now, Phase 6's MCP tools later) in one response.
    """

    max_chars: int = 30000
    max_files: int = 20
    max_graph_nodes: int = 100


class McpConfig(BaseModel):
    enabled: bool = True
    # Wall-clock budget for one MCP tool call (blueprint: "timeout
    # enforcement"). Applied via ``asyncio.wait_for`` around the
    # synchronous retrieval call -- see ``mcp/tools.py``.
    request_timeout_seconds: float = 30.0


class ApiConfig(BaseModel):
    enabled: bool = False
    bind: str = "127.0.0.1"
    port: int = 8765


class PrivacyConfig(BaseModel):
    external_ai_allowed: bool = False


class TelemetryConfig(BaseModel):
    anonymous_usage: bool = False


class RagpilotConfig(BaseModel):
    version: int = 1
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    documents: DocumentsConfig = Field(default_factory=DocumentsConfig)
    code: CodeConfig = Field(default_factory=CodeConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    mcp: McpConfig = Field(default_factory=McpConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)


_KNOWN_SECTIONS = {
    "version",
    "runtime",
    "indexing",
    "documents",
    "code",
    "search",
    "context",
    "mcp",
    "api",
    "privacy",
    "telemetry",
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _coerce_scalar(raw: str) -> Any:
    lowered = raw.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"failed to read config file {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"config file {path} must contain a mapping at the top level")
    return data


def _env_overrides(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    source: Mapping[str, str] = os.environ if environ is None else environ
    overrides: dict[str, Any] = {}
    for key, value in source.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        remainder = key[len(_ENV_PREFIX) :]
        if "__" not in remainder:
            continue
        segments = [seg.lower() for seg in remainder.split("__") if seg]
        if not segments or segments[0] not in _KNOWN_SECTIONS:
            continue
        cursor = overrides
        for segment in segments[:-1]:
            cursor = cursor.setdefault(segment, {})
        cursor[segments[-1]] = _coerce_scalar(value)
    return overrides


def load_config(
    *,
    home: Path | None = None,
    cwd: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> RagpilotConfig:
    defaults = RagpilotConfig().model_dump(mode="json")
    user_layer = _load_yaml_file(paths.user_config_path(home))
    project_layer = _load_yaml_file(paths.project_config_path(cwd))
    env_layer = _env_overrides(environ)

    merged = _deep_merge(defaults, user_layer)
    merged = _deep_merge(merged, project_layer)
    merged = _deep_merge(merged, env_layer)
    if cli_overrides:
        merged = _deep_merge(merged, cli_overrides)

    try:
        return RagpilotConfig.model_validate(merged)
    except Exception as exc:  # pydantic.ValidationError, kept broad for CLI-facing message
        raise ConfigError(f"invalid configuration: {exc}") from exc


def write_user_config(config: RagpilotConfig, *, home: Path | None = None) -> Path:
    path = paths.user_config_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    dumped = yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False)
    path.write_text(dumped, encoding="utf-8")
    return path
