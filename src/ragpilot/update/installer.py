"""Installing a newer RAGpilot release once ``checker`` has found one.

Not implemented yet: installation-method detection (install-script vs
pip vs pipx vs editable/dev), the actual download/upgrade step, and the
migration/health-check integration are this plan's Phase 5. Until then
``install_latest`` raises ``UpdateInstallNotImplementedError`` with the
manual upgrade commands, so ``ragpilot update install`` (``cli/update.py``)
exists and reports something honest rather than silently no-op-ing or
half-implementing an upgrade path.
"""

from __future__ import annotations

_INSTALL_SH_URL = "https://raw.githubusercontent.com/gzarog/Ragpilotv2/main/install.sh"
_INSTALL_PS1_URL = "https://raw.githubusercontent.com/gzarog/Ragpilotv2/main/install.ps1"


class UpdateInstallNotImplementedError(Exception):
    """Raised by every ``install_latest`` call until a later phase
    implements the real upgrade path -- see this module's docstring.
    """


def install_latest() -> None:
    raise UpdateInstallNotImplementedError(
        "`ragpilot update install` is not implemented yet in this RAGpilot "
        "version. Upgrade manually for now:\n\n"
        f"    curl -fsSL {_INSTALL_SH_URL} | sh\n\n"
        f"(Windows: irm {_INSTALL_PS1_URL} | iex)\n\n"
        "or, for a pip install: "
        'python -m pip install --upgrade "git+https://github.com/gzarog/Ragpilotv2.git@<tag>"'
    )
