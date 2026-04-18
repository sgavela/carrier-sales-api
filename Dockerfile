# ── Stage 1: build deps in an isolated venv ───────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ── Stage 2: lean runtime image ───────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user for security
RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

# Pull in the pre-built venv from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only what the app needs to run
COPY app/      app/
COPY data/     data/
COPY scripts/  scripts/

# data/ is a volume mount at runtime — ensure the dir exists and is owned by appuser
RUN mkdir -p data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
