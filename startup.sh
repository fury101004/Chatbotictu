#!/bin/sh
set -eu

PORT="${PORT:-8000}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"

# On Azure App Service, create persistent ChromaDB directory
if [ -n "${WEBSITE_SITE_NAME:-}" ]; then
  mkdir -p /home/data/chroma 2>/dev/null || true
fi

exec python -m uvicorn config.asgi:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers "${WEB_CONCURRENCY}"
