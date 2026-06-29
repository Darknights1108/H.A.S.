# HAS Backend

FastAPI + SQLAlchemy + Alembic + APScheduler。

## 本地开发

```bash
cd backend
poetry install
cp .env.example .env          # 按需修改 DATABASE_URL
# 确保本地有一个空的 Postgres,且 DATABASE_URL 指向它
poetry run alembic upgrade head   # 初始迁移会执行 ../db/schema.sql
poetry run uvicorn app.main:app --reload
```

打开 http://localhost:8000/docs 看 API。
试 `GET /api/health` 和 `GET /api/settings`(应返回 4 条默认设置)。

## 数据库迁移说明

- `db/schema.sql` 是 v1 的权威 DDL(枚举、约束、触发器、设置 seed)。
- 初始迁移 `alembic/versions/0001_initial.py` 直接执行该文件。
- 之后改表:改 `app/models.py` → `poetry run alembic revision --autogenerate -m "..."`。
  ⚠️ autogenerate **不会**自动识别触发器/部分自定义约束,需在迁移里手动 `op.execute(...)`。

## Docker

整个栈见根目录 `docker-compose.yml`。
