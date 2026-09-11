from __future__ import annotations

from pathlib import Path

import yaml

from ragpilot.core.config import load_config


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_defaults_used_when_nothing_else_set(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    config = load_config(home=home, cwd=cwd, environ={})
    assert config.runtime.log_level == "info"
    assert config.indexing.max_file_size_mb == 100


def test_user_config_overrides_defaults(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _write_yaml(home / "config.yaml", {"runtime": {"log_level": "warning"}})
    config = load_config(home=home, cwd=cwd, environ={})
    assert config.runtime.log_level == "warning"


def test_project_config_overrides_user_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    _write_yaml(home / "config.yaml", {"runtime": {"log_level": "warning"}})
    _write_yaml(cwd / ".ragpilot.yaml", {"runtime": {"log_level": "error"}})
    config = load_config(home=home, cwd=cwd, environ={})
    assert config.runtime.log_level == "error"


def test_env_var_overrides_project_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    _write_yaml(home / "config.yaml", {"runtime": {"log_level": "warning"}})
    _write_yaml(cwd / ".ragpilot.yaml", {"runtime": {"log_level": "error"}})
    config = load_config(
        home=home, cwd=cwd, environ={"RAGPILOT_RUNTIME__LOG_LEVEL": "debug"}
    )
    assert config.runtime.log_level == "debug"


def test_cli_override_wins_over_everything(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    _write_yaml(home / "config.yaml", {"runtime": {"log_level": "warning"}})
    _write_yaml(cwd / ".ragpilot.yaml", {"runtime": {"log_level": "error"}})
    config = load_config(
        home=home,
        cwd=cwd,
        environ={"RAGPILOT_RUNTIME__LOG_LEVEL": "debug"},
        cli_overrides={"runtime": {"log_level": "critical"}},
    )
    assert config.runtime.log_level == "critical"


def test_updates_defaults(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    config = load_config(home=home, cwd=cwd, environ={})
    assert config.updates.enabled is True
    assert config.updates.check_interval_hours == 24
    assert config.updates.notify is True
    assert config.updates.channel == "stable"


def test_updates_env_var_overrides(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    config = load_config(
        home=home,
        cwd=cwd,
        environ={
            "RAGPILOT_UPDATES__ENABLED": "false",
            "RAGPILOT_UPDATES__CHECK_INTERVAL_HOURS": "6",
        },
    )
    assert config.updates.enabled is False
    assert config.updates.check_interval_hours == 6


def test_env_var_type_coercion(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    config = load_config(
        home=home,
        cwd=cwd,
        environ={
            "RAGPILOT_RUNTIME__MAX_WORKERS": "12",
            "RAGPILOT_INDEXING__FOLLOW_SYMLINKS": "true",
        },
    )
    assert config.runtime.max_workers == 12
    assert config.indexing.follow_symlinks is True


def test_search_defaults_preserve_existing_semantic_behavior(tmp_path: Path) -> None:
    """Blueprint sections 18/31/32: the new knobs default to what the
    codebase already did before this redesign -- ``lazy_semantic`` off
    (semantic search always attached once ``search.semantic`` is on) and
    ``vector.engine="auto"`` (tries USearch, falls back to brute-force).
    """
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    config = load_config(home=home, cwd=cwd, environ={})
    assert config.search.lazy_semantic is False
    assert config.search.semantic_top_k == 30
    assert config.search.vector.engine == "auto"
    assert config.search.vector.rebuild_deleted_ratio == 0.15
    assert config.search.cache.enabled is True
    assert config.search.cache.max_queries == 256


def test_nested_search_vector_env_override(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    config = load_config(
        home=home,
        cwd=cwd,
        environ={"RAGPILOT_SEARCH__VECTOR__ENGINE": "bruteforce"},
    )
    assert config.search.vector.engine == "bruteforce"


def test_unrelated_env_vars_are_ignored(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    config = load_config(
        home=home, cwd=cwd, environ={"RAGPILOT_HOME": "/somewhere", "PATH": "/bin"}
    )
    assert config.runtime.log_level == "info"
