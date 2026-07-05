#!/usr/bin/env bash
# Start the RIE JSON API. Default port 8021 (8020 is often taken by the CIE reference server).
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m uvicorn server.main:app --port "${PORT:-8021}" --reload
