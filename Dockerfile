# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

# Cài compiler nhẹ, tránh các gói nặng
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make libgomp1 curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean && apt-get autoremove -y

# Tạo user không phải root
RUN useradd -m -s /bin/bash appuser
WORKDIR /app
RUN chown appuser:appuser /app
USER appuser

ENV PATH="/home/appuser/.local/bin:${PATH}"

# Copy requirements và cài đặt
COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào container
COPY --chown=appuser:appuser . .

EXPOSE 8000

CMD ["uvicorn", "config.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

