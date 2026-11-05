#!/usr/bin/env bash
# Shim kept for one minor release (ticket D6): the tool is now `gk`.
# Same arguments as before: ./genkey.sh EMAIL [PLATFORM] [HOSTNAME] [PROFILE]
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v gk >/dev/null 2>&1; then
    exec gk "$@"
fi
PYTHONPATH="$HERE/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m gk "$@"
