#!/usr/bin/env bash
set -e

echo "Waiting for DB & running migrations..."
until alembic upgrade head; do
  echo "DB not ready, retrying in 2s..."
  sleep 2
done

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
