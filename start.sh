#!/usr/bin/env sh
# macOS / Linux launcher.  Windows: use start.bat instead.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  exec python3 tools/serve.py
elif command -v python >/dev/null 2>&1; then
  exec python tools/serve.py
else
  echo "Python 3 not found. Install it first, then run this file again."
  exit 1
fi
