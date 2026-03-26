#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# Ensure local package imports like `import src...` work from any caller CWD.
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}"

MODE="${BOT_MODE:-dry-run}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

if [ "$#" -gt 0 ]; then
  exec python3 -m src "$@"
fi

exec python3 -m src --mode "${MODE}" --log-level "${LOG_LEVEL}"
