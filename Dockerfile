FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEMO_WEB_HOST=0.0.0.0 \
    SPLUNK_MCP_HOST=0.0.0.0 \
    TICKET_MCP_HOST=0.0.0.0 \
    DEMO_DATABASE_PATH=/app/data/demo.db

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

COPY data ./data

EXPOSE 8100 8101 8102

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/api/health', timeout=2)"

CMD ["mcp-service-demo", "run"]

