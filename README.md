# HAS — Hiring Automation System

通过简历 + 申请表筛选候选人、打分(High/Medium/Low)、自动排面试。首个用例:MCMC RISE 实习项目。

## 架构

| 层 | 选型 |
|----|------|
| 前端 | Next.js + TypeScript |
| 后端 | FastAPI |
| AI 编排 | LangGraph + Claude(后续) |
| 数据库 | PostgreSQL (+ pgvector,按需) |
| 定时任务 | APScheduler(shortlist 自动淘汰) |

## 目录

```
db/           schema.sql — 权威 DDL(枚举、约束、触发器、设置 seed)
backend/      FastAPI + SQLAlchemy + Alembic + APScheduler
frontend/     Next.js admin dashboard
docker-compose.yml
```

## 一键起栈(Docker)

```bash
docker compose up --build
```

- 后端 API:http://localhost:8000/docs
- 前端:http://localhost:3000(应显示 4 条默认设置 = 闭环打通)
- Postgres:localhost:5432(has / has)

后端容器启动时自动跑 `alembic upgrade head` 建表。

## 本地分别开发

见 `backend/README.md`。前端:

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

## 状态

- [x] 数据模型 + schema
- [x] 脚手架(最小闭环:前端 → 后端 → DB)
- [ ] 打分引擎(简历解析 + 硬门槛/加分 → band)
- [ ] 排期 API(面试官认领 / 候选人选时段 / 撤回改选)
- [ ] 邮件草稿(invite / offer / reject)
- [ ] Admin 设置页
```
