FROM python:3.12-slim AS base

RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY requirements-tools.txt .
RUN pip install --no-cache-dir -r requirements-tools.txt

COPY src/ ./src/
COPY tools/ ./tools/

USER appuser

ENV MCP_TRANSPORT=http \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

CMD ["python", "-m", "tools.policy_rules.server"]
