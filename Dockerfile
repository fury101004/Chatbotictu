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
USER appuser

ENV PATH="/home/appuser/.local/bin:${PATH}"
ARG PYTORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu

# Copy requirements va cai dat
COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --index-url "${PYTORCH_CPU_INDEX_URL}" "torch==2.8.0" && \
    grep -vi '^torch==' requirements.txt > /tmp/requirements-no-torch.txt && \
    pip install --no-cache-dir -r /tmp/requirements-no-torch.txt && \
    rm -f /tmp/requirements-no-torch.txt

# Copy toan bo code vao container
COPY --chown=appuser:appuser . .

EXPOSE 8000

CMD ["sh", "/app/startup.sh"]

