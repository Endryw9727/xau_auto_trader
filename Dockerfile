# XAU Auto Trader V2 — Production Docker Image
# Multi-stage build for minimal image size

# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends     gcc     libffi-dev     && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

WORKDIR /app

# Create non-root user for security
RUN groupadd -r trader && useradd -r -g trader trader

# Copy installed packages from builder
COPY --from=builder /root/.local /home/trader/.local
ENV PATH=/home/trader/.local/bin:$PATH

# Copy application code
COPY --chown=trader:trader src/ ./src/
COPY --chown=trader:trader scripts/ ./scripts/
COPY --chown=trader:trader tests/ ./tests/
COPY --chown=trader:trader config.yaml .
COPY --chown=trader:trader pytest.ini .
COPY --chown=trader:trader .env.example .

# Create data directories
RUN mkdir -p data/raw data/database reports/backtests reports/paper_trading     reports/diagnostics reports/demo_execution reports/strategy_lab     data/models data/models/checkpoints &&     chown -R trader:trader data reports

USER trader

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3     CMD python -c "import src.settings; src.settings.load_settings()" || exit 1

# Default command
CMD ["python", "-m", "src.main"]
