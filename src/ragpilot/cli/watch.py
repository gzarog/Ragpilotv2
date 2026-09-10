"""``ragpilot watch`` -- foreground, blocking daemon loop attached to the
terminal. This is the same daemon loop ``ragpilot daemon start`` runs
detached in the background (``cli/daemon.py`` spawns exactly this
command as its child process).

Deliberately thin, mirroring Phase 6's ``serve --mcp`` (``cli/serve.py``):
the blocking wait-for-signal loop below is the only part of this module,
and it is not unit-tested directly -- ``service/daemon.py``'s ``Daemon``
class is where all the actual logic (watcher wiring, debounce,
reconciliation, offline/online transitions, graceful shutdown) lives,
fully unit-tested independently of any real signal or terminal.
"""

from __future__ import annotations

import signal
import time
from types import FrameType

from ragpilot.core.lifecycle import AppContext
from ragpilot.service.daemon import Daemon

from ._common import cli_command, error_console

_IDLE_POLL_SECONDS = 0.2


@cli_command
def watch() -> None:
    with AppContext.bootstrap() as ctx:
        # A dedicated lock name (not "index") -- held for this command's
        # entire lifetime is exactly what should prevent a second
        # `ragpilot watch`/daemon from starting concurrently, whereas
        # `ragpilot index` and each of this daemon's own indexing passes
        # (service/daemon.py) only ever hold "index" briefly, per pass.
        lock = ctx.acquire_lock("watch")
        try:
            daemon = Daemon(ctx)
            stop_requested = False

            def _handle_signal(signum: int, frame: FrameType | None) -> None:
                nonlocal stop_requested
                stop_requested = True

            signal.signal(signal.SIGINT, _handle_signal)
            signal.signal(signal.SIGTERM, _handle_signal)

            error_console.print("[bold]RAGpilot watch: daemon starting...[/bold]")
            daemon.start()
            try:
                while not stop_requested:
                    time.sleep(_IDLE_POLL_SECONDS)
            finally:
                error_console.print("[bold]RAGpilot watch: shutting down...[/bold]")
                daemon.stop()
        finally:
            lock.release()
