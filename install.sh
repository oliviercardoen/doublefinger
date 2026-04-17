#!/bin/bash
set -e

# Resolve the absolute path of the repository root regardless of where the
# script is called from. REPO_DIR is used both at install time and written
# verbatim into the launcher so it never becomes a stale variable reference.
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

LAUNCHER=/usr/local/bin/doublefinger
VENV="$REPO_DIR/.venv"

# ── 1. Check python3 availability ─────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is not installed or not in PATH." >&2
    echo "Install it with: sudo apt install python3" >&2
    exit 1
fi

# ── 2. Create venv if it does not exist (idempotent) ──────────────────────────
if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment at $VENV ..."
    python3 -m venv "$VENV"
fi

# ── 3 & 4. Install dependencies ───────────────────────────────────────────────
echo "Installing dependencies from requirements.txt ..."
if ! "$VENV/bin/pip" install --quiet -r "$REPO_DIR/requirements.txt"; then
    echo "Error: pip install failed. Check your network connection and requirements.txt." >&2
    exit 1
fi

# ── 5. Install Playwright browser ─────────────────────────────────────────────
echo "Installing Playwright chromium ..."
"$VENV/bin/playwright" install chromium

# ── 6 & 7. Write the launcher to /usr/local/bin ───────────────────────────────
# The actual REPO_DIR path is expanded at install time so the launcher works
# in any working directory without needing to activate the venv.
LAUNCHER_CONTENT="#!/bin/bash
exec \"$REPO_DIR/.venv/bin/python\" \"$REPO_DIR/doublefinger.py\" \"\$@\""

write_launcher() {
    echo "$LAUNCHER_CONTENT" > "$LAUNCHER"
    chmod +x "$LAUNCHER"
}

if [ -w "$(dirname "$LAUNCHER")" ]; then
    write_launcher
else
    echo "Writing to $LAUNCHER requires elevated privileges — running with sudo ..."
    echo "$LAUNCHER_CONTENT" | sudo tee "$LAUNCHER" > /dev/null
    sudo chmod +x "$LAUNCHER"
fi

# ── 8. Success ─────────────────────────────────────────────────────────────────
echo "doublefinger installed. Run: doublefinger --help"
