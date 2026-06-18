#!/bin/sh
set -eu

PORT="${PORT:-8000}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"

_file_size() {
  if [ -f "$1" ]; then
    wc -c < "$1" | tr -d ' '
  else
    echo 0
  fi
}

_is_truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

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

_bootstrap_vectorstore_from_image() {
  src="/app/vectorstore"
  dest="${VECTORSTORE_DIR}"
  src_db="$src/chroma.sqlite3"
  dest_db="$dest/chroma.sqlite3"
  min_bytes="${VECTORSTORE_MIN_BYTES:-10485760}"

  if [ ! -f "$src_db" ]; then
    echo "[BOOTSTRAP] No bundled chroma.sqlite3 at $src_db"
    return 0
  fi

  src_size=$(_file_size "$src_db")
  dest_size=$(_file_size "$dest_db")
  should_copy=0

  if _is_truthy "${VECTORSTORE_FORCE_RESEED:-0}"; then
    should_copy=1
    echo "[BOOTSTRAP] VECTORSTORE_FORCE_RESEED enabled"
  elif [ ! -f "$dest_db" ]; then
    should_copy=1
  elif [ "$src_size" -gt "$min_bytes" ] && [ "$dest_size" -lt "$min_bytes" ]; then
    should_copy=1
    echo "[BOOTSTRAP] Persistent chroma.sqlite3 looks empty/small (${dest_size}B < ${min_bytes}B)"
  elif [ "$src_size" -gt "$dest_size" ]; then
    should_copy=1
    echo "[BOOTSTRAP] Bundled chroma.sqlite3 is newer/larger (${src_size}B > ${dest_size}B)"
  fi

  if [ "$should_copy" = "1" ]; then
    echo "[BOOTSTRAP] Seed vectorstore ${src} -> ${dest} (src=${src_size}B dest=${dest_size}B)"
    mkdir -p "$dest"
    rm -rf "${dest:?}/"*
    cp -a "$src/." "$dest/"
    echo "[BOOTSTRAP] Vectorstore seeded, new size=$(_file_size "$dest_db")B"
  else
    echo "[BOOTSTRAP] Keep existing vectorstore at ${dest} (${dest_size}B)"
  fi
}

_bootstrap_file_if_missing() {
  src="$1"
  dest="$2"
  min_bytes="${3:-1024}"

  if [ ! -f "$src" ]; then
    echo "[BOOTSTRAP] Skip (no source file): $src"
    return 0
  fi

  src_size=$(_file_size "$src")
  dest_size=$(_file_size "$dest")
  should_copy=0

  if _is_truthy "${APP_DATA_FORCE_RESEED:-0}"; then
    should_copy=1
  elif [ ! -f "$dest" ]; then
    should_copy=1
  elif [ "$src_size" -gt "$min_bytes" ] && [ "$dest_size" -lt "$min_bytes" ]; then
    should_copy=1
  elif [ "$src_size" -gt "$dest_size" ]; then
    should_copy=1
  fi

  if [ "$should_copy" = "1" ]; then
    mkdir -p "$(dirname "$dest")"
    echo "[BOOTSTRAP] Copy $src -> $dest (src=${src_size}B dest=${dest_size}B)"
    cp -a "$src" "$dest"
  else
    echo "[BOOTSTRAP] Keep existing file $dest (${dest_size}B)"
  fi
}

# On Azure App Service, redirect HuggingFace cache and vectorstore away from
# read-only /home/site before Python imports config.settings.
if [ -n "${WEBSITE_SITE_NAME:-}" ]; then
  mkdir -p /home/data/vectorstore /home/data/app /home/data/hf-cache /home/data/transformers /home/data/sentence-transformers /home/data/.cache/torch 2>/dev/null || true

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
  case "${DATA_DIR:-}" in
    ""|/app/data|/app/data/*|/home/site|/home/site/*) DATA_DIR="/home/data/app" ;;
  esac
  case "${DB_PATH:-}" in
    ""|/app/data/bot_config.db|/home/site/data/bot_config.db|/home/site|/home/site/*) DB_PATH="${DATA_DIR}/bot_config.db" ;;
  esac
  case "${RAG_UPLOAD_ROOT:-}" in
    ""|/app/data/rag_uploads|/app/data/rag_uploads/*|/home/site/data/rag_uploads|/home/site|/home/site/*) RAG_UPLOAD_ROOT="${DATA_DIR}/rag_uploads" ;;
  esac

  export HF_HOME HUGGINGFACE_HUB_CACHE TRANSFORMERS_CACHE SENTENCE_TRANSFORMERS_HOME TORCH_HOME XDG_CACHE_HOME VECTORSTORE_DIR DATA_DIR DB_PATH RAG_UPLOAD_ROOT
  mkdir -p "${HF_HOME}" "${HUGGINGFACE_HUB_CACHE}" "${TRANSFORMERS_CACHE}" "${SENTENCE_TRANSFORMERS_HOME}" "${TORCH_HOME}" "${XDG_CACHE_HOME}" "${VECTORSTORE_DIR}" "${DATA_DIR}" "${RAG_UPLOAD_ROOT}" "$(dirname "${DB_PATH}")" 2>/dev/null || true

  echo "=== Azure Startup Paths (before Python boot) ==="
  echo "  VECTORSTORE_DIR=${VECTORSTORE_DIR}"
  echo "  DATA_DIR=${DATA_DIR}"
  echo "  RAG_UPLOAD_ROOT=${RAG_UPLOAD_ROOT}"
  echo "  DB_PATH=${DB_PATH}"
  echo "  HF_HOME=${HF_HOME}"
  echo "  HUGGINGFACE_HUB_CACHE=${HUGGINGFACE_HUB_CACHE}"
  echo "  TRANSFORMERS_CACHE=${TRANSFORMERS_CACHE}"
  echo "  SENTENCE_TRANSFORMERS_HOME=${SENTENCE_TRANSFORMERS_HOME}"
  echo "  TORCH_HOME=${TORCH_HOME}"
  echo "  XDG_CACHE_HOME=${XDG_CACHE_HOME}"
  echo "================================================"

  # Seed persistent storage from image-bundled data.
  _bootstrap_vectorstore_from_image
  _bootstrap_copy_tree_if_missing /app/data/rag_uploads "${RAG_UPLOAD_ROOT}" ""
  _bootstrap_file_if_missing /app/data/bot_config.db "${DB_PATH}" 1024
fi

exec python -m uvicorn config.asgi:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers "${WEB_CONCURRENCY}"
