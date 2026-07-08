# HAS — Hiring Automation System

Screens candidates from resume + application form, scores them (High/Medium/Low),
and automates online interview scheduling. First use case: the MCMC RISE
internship programme.

## Architecture

| Layer | Choice |
|-------|--------|
| Frontend | Next.js + TypeScript |
| Backend | FastAPI |
| AI | LLM layer with Anthropic (preferred) / OpenAI fallback |
| Database | PostgreSQL (+ pgvector when semantic search is needed) |
| Scheduled jobs | APScheduler (auto-expiry timers, auto-send) |
| Object storage | MinIO (resume files) |

## Layout

```
db/           schema.sql — authoritative v1 DDL (enums, constraints, triggers, setting seeds)
backend/      FastAPI + SQLAlchemy + Alembic + APScheduler
frontend/     Next.js dashboard + candidate pages
docker-compose.yml
```

## One-click start

**Windows: double-click `start-has.bat`** — starts Docker Desktop if needed,
brings up the containers, waits for the services, then opens the browser.
Stop with `stop-has.bat` (data is kept); after code changes run
`start-has.bat build` to rebuild images.

Or manually:

```bash
docker compose up --build
```

- Backend API: http://localhost:8000/docs
- Frontend: http://localhost:3000
- Postgres: localhost:5432 (has / has)
- MinIO console: http://localhost:9001

The backend container runs `alembic upgrade head` automatically on start.

## Local development

See `backend/README.md`. Frontend:

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

## Status

- [x] Data model + schema
- [x] Scaffold (minimal loop: frontend → backend → DB)
- [x] Scheduling module: interviewer slot claiming / candidate slot picking
      (hold → confirm → unlimited reschedules) / row-lock concurrency safety
  - Candidate page `/booking/{token}` (no login, token-based)
  - Staff page `/admin/slots` (grid generation, claim/withdraw, bulk actions)
- [x] Scoring engine: knockout (hard requirements) + bonus points → High/Medium/Low
  - High/Medium → shortlist (admin reviews, then Approve drafts the invite);
    Low → automatic rejection letter + talent bank
  - Two-step application: `/apply` (academics) → `/apply/skills` (skill assessment;
    scoring inputs are derived from the skill list)
  - Reasoning text polished by the LLM when a key is configured, rule-based fallback
  - Auto-expiry timers with configurable windows (unreviewed shortlist / unresponsive candidate)
- [x] Jobs admin `/admin/jobs`: paste a JD → AI digests it into a screening profile
      (summary + must-have + nice-to-have) plus fixed-form rules → editable → create
  - Per-job rules in `job.requirements`, applied dynamically by the scoring engine
- [x] Resume upload + LLM parsing: MinIO storage (PDF/DOCX/TXT ≤ 5MB)
  - Background parsing (never blocks submission): text extraction → structured
    LLM extraction (education/experience/skills/AI evidence)
  - Cross-checks resume against form claims (CONFIRMED / MISMATCH / NOT FOUND)
  - Evaluates the resume against the job's screening profile → per-criterion
    match with evidence + 0-100 match score + verdict
  - Staff-wide resume library at `/admin/resumes` (view inline / download)
- [x] Email sending: outbox `/admin/emails` (preview → manual send); Gmail SMTP
  - Booking confirmation/reschedule emails send automatically (factual content)
  - Offer letters send immediately on Accept; low-band rejection letters send
    automatically after a configurable review window; all other letters are manual
- [x] Interview outcomes `/admin/outcomes`: awaiting-decision queue (interview
      time passed) with Accept/Reject + confirmation, upcoming interviews,
      recent decisions
- [x] Analytics `/admin/analytics`: overview cards, hiring funnel, band
      distribution, rejection reasons, per-job stats, 14-day trend, slot
      utilisation, interviewer load — plus Excel export (multi-sheet workbook
      with raw application/interview detail)
- [x] Authentication: passwordless Email OTP (6-digit code) + email allowlist +
      server-side sessions (see `docs/auth-email-otp.md`)
  - Two-step `/login` (Send Code → Verify); hashed codes, 10-minute expiry,
    single-use, locked after 5 wrong attempts
  - Allowlist management `/admin/allowlist` (roles / enable / audit trail)
  - Interviewers can only act as themselves; admin-only management pages
  - First admin seeded from the `ADMIN_EMAIL` environment variable
- [x] Panel notifications: interviewers get an email when a candidate books or
      reschedules their slot
- [x] Settings page `/admin/settings`: review windows, slot length, working
      hours, panel cap, reschedule limit, company name, invite email template —
      validated, effective immediately
- [ ] Real meeting links (currently a Jitsi placeholder)
