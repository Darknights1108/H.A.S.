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
- [x] 排期模块:面试官认领 / 候选人选时段(hold→确认→不限次改期)/ 并发行锁
  - 候选人页 `/booking/{token}`(免登录,凭 token)
  - 管理页 `/admin/slots`(生成时段网格、认领/撤回)
  - 确认/改期自动生成邮件草稿(发送待接入)
- [x] 打分引擎:提交即打分,硬门槛(knockout)+ 加分(bonus)→ High/Medium/Low
  - High/Medium → shortlist(admin 审查后 Approve 草拟邀请信);Low → 自动婉拒 + talent bank
  - 申请表 `/apply`(公开),审查队列 `/admin/applications`(band、理由、Approve/Reject)
  - 理由生成:有 `ANTHROPIC_API_KEY` 用 Claude 润色,否则规则模板(可降级)
  - 超时无人审自动淘汰 + 婉拒信草稿(APScheduler,天数可配)
- [x] 职位管理 `/admin/jobs`:贴 JD → AI 解析成筛选规则(chat box)→ 预览修改 → 创建
  - 每个职位独立规则(`job.requirements`),打分动态执行;开/关职位
  - AI 解析需 `ANTHROPIC_API_KEY`,无 key 时降级为手动填规则表单
- [x] 简历上传 + LLM 解析:MinIO 对象存储(PDF/DOCX/TXT ≤5MB)
  - 后台线程解析(不阻塞提交):文本提取 → LLM 结构化抽取(教育/经历/技能/AI 证据)
  - ★ 与表单声明交叉核对(consistency notes:CONFIRMED / MISMATCH / NOT FOUND)
  - 审查页展开可见摘要+核对结果,可下载原文件;打分仍以表单为主数据源
- [x] 邮件发送:Outbox `/admin/emails`(草稿预览 → 人工 Send);Gmail SMTP(App Password,`.env` 配 `SMTP_*`)
  - 预约确认/改期信自动发送(纯事实性);邀请/婉拒/offer 走 Outbox 人工审核
  - SMTP 未配置时草稿保留,页面有提示
- [x] 面试结果处理:admin 在审查页对已排面试标记 Pass / Fail
  - Pass → application=passed + offer 信草稿;Fail → rejected(interview_failed)+ 婉拒信草稿(留 talent bank)
  - 草稿进 Outbox 人工审核发送;pipeline 全链路闭环
- [x] Analytics `/admin/analytics`:总览卡片、招聘漏斗、band 分布、淘汰原因、各职位统计、近14天趋势、时段利用率、面试官负载
- [x] 认证:Magic Link(免密码)+ 邮箱白名单 + Session Cookie(详见 `docs/auth-magic-link.md`)
  - 登录页 `/login`;白名单管理 `/admin/allowlist`(角色/启停/审计)
  - 面试官登入后只能以自己身份认领时段;admin 才能进审查/职位/邮件页
  - 首个 admin 由 `ADMIN_EMAIL` 环境变量启动时写入
- [x] 双 timer:无人审(未发邀请)/ 候选人无响应(邀请发出 N 天未预约),互不误伤,天数均可配
- [x] 面试官通知:候选人确认/改期预约后,panel 面试官收到邮件(时间 + 候选人 + 会议链接)
- [x] Admin 设置页 `/admin/settings`:审查期限/时段长度/panel 上限/改期上限/公司署名,带取值校验,改动即时生效
- [ ] 真实会议链接(目前为 Jitsi 占位)
```
