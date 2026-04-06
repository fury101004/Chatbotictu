# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

# CĂ i compiler nháº¹, trĂ¡nh cĂ¡c gĂ³i náº·ng
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make libgomp1 curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean && apt-get autoremove -y

# Táº¡o user khĂ´ng pháº£i root
RUN useradd -m -s /bin/bash appuser
WORKDIR /app
RUN chown appuser:appuser /app
USER appuser

ENV PATH="/home/appuser/.local/bin:${PATH}"

# CĂ i PyTorch CPU-only phiĂªn báº£n 2.1.0
RUN pip install --no-cache-dir torch==2.1.0+cpu --index-url https://download.pytorch.org/whl/cpu

# Copy requirements vĂ  cĂ i Ä‘áº·t
COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy toĂ n bá»™ code vĂ o container
COPY --chown=appuser:appuser . .

EXPOSE 8000

CMD ["uvicorn", "config.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

