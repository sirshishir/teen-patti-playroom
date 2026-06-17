# SnipeBot Dockerfile — multi-stage build
#
# WARNING: Never add .env to this image. Secrets must be injected at runtime
# via environment variables (fly secrets set, docker run -e, etc.). The
# .dockerignore file in this directory explicitly excludes .env.

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Install C/C++ build tools required by scipy, scikit-learn, torch, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .

# Install all Python packages into the user site-packages directory so we
# can copy only the installed packages (not the build tools) into stage 2.
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim

# Copy installed packages from the builder stage (no compiler needed at runtime)
COPY --from=builder /root/.local /root/.local

# Copy application source code
COPY . /app/snipebot

WORKDIR /app/snipebot

# Ensure user-installed packages are on PATH and importable
ENV PATH="/root/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    SNIPEBOT_DATA_DIR=/data

# Create the /data directory; on Fly.io this will be a persistent volume mount
# for the SQLite database and rotating log files. Without the volume the
# directory still exists so the container starts cleanly on first deploy.
RUN mkdir -p /data

# Run as a long-lived background worker — no HTTP server, no exposed ports.
CMD ["python", "main.py"]
