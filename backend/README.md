# HAS Backend

FastAPI + SQLAlchemy + Alembic + APScheduler.

## Local development

```bash
cd backend
poetry install
cp .env.example .env          # adjust DATABASE_URL as needed
# make sure an empty local Postgres exists and DATABASE_URL points at it
poetry run alembic upgrade head   # the initial migration executes ../db/schema.sql
poetry run uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the API.
Try `GET /api/health`.

## Database migrations

- `db/schema.sql` is the authoritative v1 DDL (enums, constraints, triggers,
  setting seeds).
- The initial migration `alembic/versions/0001_initial.py` executes that file
  directly; later changes live in their own migration files (0002+).
- To change tables: edit `app/models.py`, then
  `poetry run alembic revision --autogenerate -m "..."`.
  ⚠ autogenerate does NOT pick up triggers or some custom constraints — add
  those manually with `op.execute(...)` inside the migration.

## Docker

See `docker-compose.yml` at the repo root for the full stack.
