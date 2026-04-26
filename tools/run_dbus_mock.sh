#!/usr/bin/env bash
# tools/run_dbus_mock.sh
# ~~~~~~~~~~~~~~~~~~~~~~
# Starts the mock Sugar DataStore D-Bus service.
#
# If no DBUS_SESSION_BUS_ADDRESS is set (e.g. you're in a plain terminal,
# SSH session, or Docker), it spins up a private session bus automatically.
#
# Usage:
#   chmod +x tools/run_dbus_mock.sh
#   ./tools/run_dbus_mock.sh
#
# In a second terminal:
#   DATASTORE_BACKEND=dbus uvicorn app.main:app --reload

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# ---------------------------------------------------------------------------
# If no session bus is available, start a temporary one
# ---------------------------------------------------------------------------
PRIVATE_BUS=0

if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
    echo "No DBUS_SESSION_BUS_ADDRESS found — starting a private session bus…"
    eval "$(dbus-launch --sh-syntax)"
    PRIVATE_BUS=1
    echo "Private bus: $DBUS_SESSION_BUS_ADDRESS"
fi

# ---------------------------------------------------------------------------
# Cleanup on exit
# ---------------------------------------------------------------------------
cleanup() {
    if [[ $PRIVATE_BUS -eq 1 && -n "${DBUS_SESSION_BUS_PID:-}" ]]; then
        echo "Killing private D-Bus daemon (pid $DBUS_SESSION_BUS_PID)…"
        kill "$DBUS_SESSION_BUS_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Run the mock service
# ---------------------------------------------------------------------------
echo "Starting Mock DataStore…"
python3 tools/mock_datastore_service.py
