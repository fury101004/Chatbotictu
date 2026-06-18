#!/bin/sh
set -eu

PORT="${PORT:-8000}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"

# On Azure App Service, create persistent ChromaDB directory
if [ -n "${WEBSITE_SITE_NAME:-}" ]; then
  mkdir -p /home/data/chroma 2>/dev/null || true
  mkdir -p /home/data/hf-cache /home/data/transformers /home/data/sentence-transformers /home/data/.cache/torch 2>/dev/null || true

  case "${HF_HOME:-}" in
    ""|/home/site|/home/site/*) HF_HOME="/home/data/hf-cache" ;;
  esac
  case "${HUGGINGFACE_HUB_CACHE:-}" in
    ""|/home/site|/home/site/*) HUGGINGFACE_HUB_CACHE="${HF_HOME}/hub" ;;
  esac
  case "${TRANSFORMERS_CACHE:-}" in
    ""|/home/site|/home/site/*) TRANSFORMERS_CACHE="/home/data/transformers" ;;
  esac
  case "${SENTENCE_TRANSFORMERS_HOME:-}" in
    ""|/home/site|/home/site/*) SENTENCE_TRANSFORMERS_HOME="/home/data/sentence-transformers" ;;
  esac
  case "${TORCH_HOME:-}" in
    ""|/home/site|/home/site/*) TORCH_HOME="/home/data/.cache/torch" ;;
  esac
  case "${XDG_CACHE_HOME:-}" in
    ""|/home/site|/home/site/*) XDG_CACHE_HOME="/home/data/.cache" ;;
  esac
  export HF_HOME HUGGINGFACE_HUB_CACHE TRANSFORMERS_CACHE SENTENCE_TRANSFORMERS_HOME TORCH_HOME XDG_CACHE_HOME
  mkdir -p "${HF_HOME}" "${HUGGINGFACE_HUB_CACHE}" "${TRANSFORMERS_CACHE}" "${SENTENCE_TRANSFORMERS_HOME}" "${TORCH_HOME}" "${XDG_CACHE_HOME}" 2>/dev/null || true

  echo "=== Azure Cache Paths ==="
  echo "  HF_HOME=${HF_HOME}"
  echo "  HUGGINGFACE_HUB_CACHE=${HUGGINGFACE_HUB_CACHE}"
  echo "  TRANSFORMERS_CACHE=${TRANSFORMERS_CACHE}"
  echo "  SENTENCE_TRANSFORMERS_HOME=${SENTENCE_TRANSFORMERS_HOME}"
  echo "  TORCH_HOME=${TORCH_HOME}"
  echo "  XDG_CACHE_HOME=${XDG_CACHE_HOME}"
  echo "========================="
fi

exec python -m uvicorn config.asgi:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers "${WEB_CONCURRENCY}"
