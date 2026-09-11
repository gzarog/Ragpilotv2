#!/bin/sh
# Installs the RAGpilot CLI: downloads the source for $RAGPILOT_REF (default:
# main), creates an isolated virtual environment, installs the package into
# it, and links the `ragpilot` executable onto a per-user bin directory.
#
# Requires Python 3.12+ already on PATH -- this script does not install
# Python itself. See README.md's Installation section for details.
set -eu

REPO="gzarog/Ragpilotv2"
REF="${RAGPILOT_REF:-main}"
INSTALL_DIR="${RAGPILOT_INSTALL_DIR:-$HOME/.ragpilot}"
APP_DIR="$INSTALL_DIR/app"
VENV_DIR="$INSTALL_DIR/venv"
BIN_DIR="${RAGPILOT_BIN_DIR:-$HOME/.local/bin}"

find_python() {
    for candidate in python3.13 python3.12 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            version="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")"
            major="${version%%.*}"
            minor="${version#*.}"
            if [ "$major" -eq 3 ] && [ "$minor" -ge 12 ] 2>/dev/null; then
                echo "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON="$(find_python)" || {
    echo "error: RAGpilot requires Python 3.12+, but no suitable interpreter was found on PATH." >&2
    echo "Install Python 3.12 or newer (https://www.python.org/downloads/) and re-run this script." >&2
    exit 1
}
echo "Using $("$PYTHON" --version) at $(command -v "$PYTHON")"

TARBALL="$(mktemp)"
trap 'rm -f "$TARBALL"' EXIT
echo "Downloading RAGpilot ($REF)..."
DOWNLOAD_URL="https://github.com/$REPO/archive/refs/heads/$REF.tar.gz"
# GitHub's archive/codeload endpoint can briefly 404 a branch that was just
# pushed (its tarball cache lags the push by a few seconds) -- retry a
# handful of times with linear backoff before giving up, rather than
# failing outright on what is usually a transient race.
attempt=1
max_attempts=5
until curl -fsSL "$DOWNLOAD_URL" -o "$TARBALL"; do
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "error: failed to download $DOWNLOAD_URL after $attempt attempts" >&2
        exit 1
    fi
    echo "Download attempt $attempt failed, retrying in ${attempt}s..." >&2
    sleep "$attempt"
    attempt=$((attempt + 1))
done

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
tar -xzf "$TARBALL" -C "$APP_DIR" --strip-components=1

echo "Creating virtual environment at $VENV_DIR..."
rm -rf "$VENV_DIR"
"$PYTHON" -m venv "$VENV_DIR"

echo "Installing RAGpilot (this downloads its dependencies, including torch -- may take a few minutes)..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "$APP_DIR"

mkdir -p "$BIN_DIR"
ln -sf "$VENV_DIR/bin/ragpilot" "$BIN_DIR/ragpilot"
echo "RAGpilot installed: $BIN_DIR/ragpilot"

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        echo ""
        echo "warning: $BIN_DIR is not on your PATH."
        echo "Add this to your shell profile (~/.bashrc, ~/.zshrc, ~/.profile, ...):"
        echo "  export PATH=\"$BIN_DIR:\$PATH\""
        ;;
esac

echo ""
echo "Run 'ragpilot version' to verify, then 'ragpilot init' to get started."
