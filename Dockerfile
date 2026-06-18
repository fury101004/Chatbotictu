# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

# Cai compiler nhe, tranh cac goi nang
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make libgomp1 curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean && apt-get autoremove -y

RUN useradd -m -s /bin/bash appuser
WORKDIR /app

ENV VECTORSTORE_DIR=/home/data/vectorstore
ENV HF_HOME=/home/data/hf-cache
ENV HUGGINGFACE_HUB_CACHE=/home/data/hf-cache/hub
ENV TRANSFORMERS_CACHE=/home/data/transformers
ENV SENTENCE_TRANSFORMERS_HOME=/home/data/sentence-transformers
ENV TORCH_HOME=/home/data/.cache/torch
ENV XDG_CACHE_HOME=/home/data/.cache
ARG PYTORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu

# Install Python deps system-wide so Azure startup can use /usr/local/bin/python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --index-url "${PYTORCH_CPU_INDEX_URL}" "torch==2.8.0" && \
    grep -vi '^torch==' requirements.txt > /tmp/requirements-no-torch.txt && \
    pip install --no-cache-dir -r /tmp/requirements-no-torch.txt && \
    rm -f /tmp/requirements-no-torch.txt

# Persistent dirs + model cache baked into image
RUN mkdir -p /home/data/vectorstore /home/data/hf-cache /home/data/transformers /home/data/sentence-transformers /home/data/.cache/torch /home/data/app/rag_uploads

ARG EMBEDDING_MODEL_NAME=paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL_NAME}')"

# Copy bundled app + knowledge artifacts
COPY . .
RUN chown -R appuser:appuser /app /home/data

USER appuser
ENV PATH="/home/appuser/.local/bin:/usr/local/bin:${PATH}"

EXPOSE 8000

CMD ["sh", "/app/startup.sh"]
