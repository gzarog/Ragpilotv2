"""``ragpilot init`` -- bootstrap the RAGpilot runtime directory."""

from __future__ import annotations

from ragpilot.core import paths
from ragpilot.core.config import RagpilotConfig, load_config, write_user_config
from ragpilot.storage.migrations import apply_migrations
from ragpilot.storage.sqlite import connect

from ._common import cli_command, console


@cli_command
def init() -> None:
    home = paths.ensure_runtime_layout()
    config_path = paths.user_config_path(home)
    if not config_path.is_file():
        write_user_config(RagpilotConfig(), home=home)
        console.print(f"Wrote default configuration to [cyan]{config_path}[/cyan]")
    else:
        load_config(home=home)  # validate the existing config, surfaces ConfigError early
        console.print(f"Using existing configuration at [cyan]{config_path}[/cyan]")

    conn = connect(paths.sources_db_path(home))
    try:
        apply_migrations(conn, "sources")
    finally:
        conn.close()

    console.print(f"[bold green]RAGpilot initialized[/bold green] at {home}")
