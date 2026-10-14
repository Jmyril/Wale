#!/usr/bin/env bash
# Start the Wale web server.
# Usage: ./run.sh            -> http://127.0.0.1:8000
#        PORT=9000 ./run.sh  -> http://127.0.0.1:9000
set -e
cd "$(dirname "$0")"
exec python3 server.py
