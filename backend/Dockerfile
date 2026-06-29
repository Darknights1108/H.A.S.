# 构建上下文 = repo 根目录(见 docker-compose.yml),以便 COPY db/
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=1.8.5 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "poetry==$POETRY_VERSION"

# 先装依赖(利用缓存)
COPY backend/pyproject.toml backend/poetry.lock* ./
RUN poetry install --no-root --only main

# 应用代码 + schema.sql
COPY backend/ ./
COPY db/ /db/
ENV HAS_SCHEMA_SQL=/db/schema.sql

RUN chmod +x ./entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
