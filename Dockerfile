# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

# Cai compiler nhe, tranh cac goi nang
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make libgomp1 curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean && apt-get autoremove -y

# Tao user khong phai root
RUN useradd -m -s /bin/bash appuser
WORKDIR /app
RUN chown appuser:appuser /app

# Tao thu muc persistent data truoc khi switch user
RUN mkdir -p /home/data/vectorstore /home/data/hf-cache /home/data/transformers /home/data/sentence-transformers /home/data/.cache && chown -R appuser:appuser /home/data

USER appuser

ENV PATH="/home/appuser/.local/bin:${PATH}"
ENV VECTORSTORE_DIR=/home/data/vectorstore
ENV HF_HOME=/home/data/hf-cache
ENV HUGGINGFACE_HUB_CACHE=/home/data/hf-cache/hub
ENV TRANSFORMERS_CACHE=/home/data/transformers
ENV SENTENCE_TRANSFORMERS_HOME=/home/data/sentence-transformers
ENV TORCH_HOME=/home/data/.cache/torch
ENV XDG_CACHE_HOME=/home/data/.cache
ARG PYTORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu

# Copy requirements va cai dat
COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --index-url "${PYTORCH_CPU_INDEX_URL}" "torch==2.8.0" && \
    grep -vi '^torch==' requirements.txt > /tmp/requirements-no-torch.txt && \
    pip install --no-cache-dir -r /tmp/requirements-no-torch.txt && \
    rm -f /tmp/requirements-no-torch.txt

# Pre-download embedding model at build time so Azure runtime does not write to /home/site
ARG EMBEDDING_MODEL_NAME=paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL_NAME}')"

# Copy toan bo code vao container (includes vectorstore/, clean_data/, datapdf/, data/rag_uploads/)
COPY --chown=appuser:appuser . .

EXPOSE 8000

CMD ["sh", "/app/startup.sh"]

