#!/bin/sh
set -eu

PORT="${PORT:-8000}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"

_bootstrap_copy_tree_if_missing() {
  src="$1"
  dest="$2"
  marker="${3:-}"

  if [ ! -d "$src" ]; then
    echo "[BOOTSTRAP] Skip (no source): $src"
    return 0
  fi

  mkdir -p "$dest"

  if [ -n "$marker" ] && [ -e "$dest/$marker" ]; then
    echo "[BOOTSTRAP] Skip (marker exists): $dest/$marker"
    return 0
  fi

  if [ -z "$marker" ] && [ -n "$(ls -A "$dest" 2>/dev/null || true)" ]; then
    echo "[BOOTSTRAP] Skip (dest not empty): $dest"
    return 0
  fi

  echo "[BOOTSTRAP] Copy $src -> $dest"
  cp -a "$src/." "$dest/"
}

_bootstrap_file_if_missing() {
  src="$1"
  dest="$2"

  if [ ! -f "$src" ]; then
    echo "[BOOTSTRAP] Skip (no source file): $src"
    return 0
  fi

  if [ -f "$dest" ]; then
    echo "[BOOTSTRAP] Skip (file exists): $dest"
    return 0
  fi

  mkdir -p "$(dirname "$dest")"
  echo "[BOOTSTRAP] Copy $src -> $dest"
  cp -a "$src" "$dest"
}

# On Azure App Service, redirect HuggingFace cache and vectorstore away from
# read-only /home/site before Python imports config.settings.
if [ -n "${WEBSITE_SITE_NAME:-}" ]; then
  mkdir -p /home/data/vectorstore /home/data/hf-cache /home/data/transformers /home/data/sentence-transformers /home/data/.cache/torch 2>/dev/null || true

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
  case "${VECTORSTORE_DIR:-}" in
    ""|/home/site|/home/site/*|/app/vectorstore|/app/vectorstore/*) VECTORSTORE_DIR="/home/data/vectorstore" ;;
  esac

  RAG_UPLOAD_ROOT="${RAG_UPLOAD_ROOT:-/home/site/data/rag_uploads}"
  DB_PATH="${DB_PATH:-/home/site/data/bot_config.db}"

  export HF_HOME HUGGINGFACE_HUB_CACHE TRANSFORMERS_CACHE SENTENCE_TRANSFORMERS_HOME TORCH_HOME XDG_CACHE_HOME VECTORSTORE_DIR RAG_UPLOAD_ROOT DB_PATH
  mkdir -p "${HF_HOME}" "${HUGGINGFACE_HUB_CACHE}" "${TRANSFORMERS_CACHE}" "${SENTENCE_TRANSFORMERS_HOME}" "${TORCH_HOME}" "${XDG_CACHE_HOME}" "${VECTORSTORE_DIR}" "$(dirname "${RAG_UPLOAD_ROOT}")" "$(dirname "${DB_PATH}")" 2>/dev/null || true

  echo "=== Azure Startup Paths (before Python boot) ==="
  echo "  VECTORSTORE_DIR=${VECTORSTORE_DIR}"
  echo "  RAG_UPLOAD_ROOT=${RAG_UPLOAD_ROOT}"
  echo "  DB_PATH=${DB_PATH}"
  echo "  HF_HOME=${HF_HOME}"
  echo "  HUGGINGFACE_HUB_CACHE=${HUGGINGFACE_HUB_CACHE}"
  echo "  TRANSFORMERS_CACHE=${TRANSFORMERS_CACHE}"
  echo "  SENTENCE_TRANSFORMERS_HOME=${SENTENCE_TRANSFORMERS_HOME}"
  echo "  TORCH_HOME=${TORCH_HOME}"
  echo "  XDG_CACHE_HOME=${XDG_CACHE_HOME}"
  echo "================================================"

  # Seed persistent storage from image-bundled data on first boot only.
  _bootstrap_copy_tree_if_missing /app/vectorstore "${VECTORSTORE_DIR}" chroma.sqlite3
  _bootstrap_copy_tree_if_missing /app/data/rag_uploads "${RAG_UPLOAD_ROOT}" ""
  _bootstrap_file_if_missing /app/data/bot_config.db "${DB_PATH}"
fi

exec python -m uvicorn config.asgi:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers "${WEB_CONCURRENCY}"
