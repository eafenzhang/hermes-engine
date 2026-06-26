# ── Hermes Engine ───────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy all application source first
COPY agent/ agent/
COPY config/ config/
COPY conversation/ conversation/
COPY mcp/ mcp/
COPY memory/ memory/
COPY provider/ provider/
COPY shared/ shared/
COPY skill/ skill/
COPY tools/ tools/
COPY main.py run.py pyproject.toml ./

# Install production dependencies + the package itself
RUN pip install --no-cache-dir -e ".[observability]" && \
    rm -rf /root/.cache

# Non-root user for production safety
RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 app && \
    chown -R app:app /app
USER app

ENV HERMES_HOST=0.0.0.0 \
    HERMES_PORT=8080

EXPOSE 8080

# Health check — relies on the /api/health endpoint (always unauthenticated).
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')" || exit 1

ENTRYPOINT ["python", "run.py"]
