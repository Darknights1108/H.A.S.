-- ============================================================================
-- Hiring Automation System (HAS) — PostgreSQL schema
-- Target: PostgreSQL 14+
-- Conventions: UUID primary keys (gen_random_uuid), timestamptz everywhere,
-- timezone fixed to MYT at the application layer
-- ============================================================================

-- gen_random_uuid() comes from pgcrypto (built-in since PG13);
-- citext provides case-insensitive email columns
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
-- CREATE EXTENSION IF NOT EXISTS vector;   -- enable when semantic search is needed (see end of file)

-- ---------------------------------------------------------------------------
-- Enum types
-- ---------------------------------------------------------------------------
CREATE TYPE application_status AS ENUM (
    'applied',       -- newly submitted
    'scored',        -- automatically scored
    'shortlisted',   -- passed screening, awaiting admin review
    'scheduled',     -- interview booked
    'interviewed',   -- interview held
    'passed',        -- accepted
    'rejected'       -- rejected
);

CREATE TYPE score_band     AS ENUM ('high', 'medium', 'low');
CREATE TYPE slot_status    AS ENUM ('empty', 'open', 'booked');
CREATE TYPE interview_status AS ENUM ('scheduled', 'completed', 'passed', 'failed', 'cancelled');
CREATE TYPE email_type     AS ENUM ('invite', 'offer', 'reject');
CREATE TYPE email_status   AS ENUM ('draft', 'sent');

-- ---------------------------------------------------------------------------
-- app_setting — global configuration (edited by admin on the settings page;
-- generic key-value store, so adding a setting needs no schema change)
-- ---------------------------------------------------------------------------
CREATE TABLE app_setting (
    key         text PRIMARY KEY,
    value       jsonb       NOT NULL,
    description text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Default values (seed)
INSERT INTO app_setting (key, value, description) VALUES
    ('shortlist_review_days', '7',    'Auto-reject shortlisted applications not reviewed within this many days'),
    ('slot_duration_minutes', '60',   'Length of each interview slot in minutes'),
    ('panel_max_interviewers', '5',   'Maximum interviewers per slot (panel cap)'),
    ('reschedule_max',        '0',    'Max reschedules after confirmation (0 = unlimited)'),
    ('company_name',          '"HAS"', 'Company name used in candidate letter signatures'),
    ('candidate_response_days', '7',   'Auto-reject if candidate has not booked within this many days after invite'),
    ('work_start_hour',       '9',    'Slot generation: working hours start (MYT)'),
    ('work_end_hour',         '18',   'Slot generation: working hours end (exclusive)'),
    ('invite_email_subject',  '"Interview invitation — {job_title}"', 'Invite email subject (supports placeholders)'),
    ('low_reject_send_days',  '2',    'Auto-send low-band rejection letters after this many days'),
    ('invite_email_template', '"Hi {candidate_name},\n\nCongratulations! You have been shortlisted for {job_title}.\n\nPlease pick an interview time that suits you using your personal booking link:\n{booking_url}\n\nAll interviews are conducted online (times in MYT, UTC+08:00).\n\nBest Regards,\n{company_name} Recruiting Team\n"', 'Invite email body template. Placeholders: {candidate_name} {job_title} {booking_url} {company_name}')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- candidate — deduplicated person (same email = same person)
-- ---------------------------------------------------------------------------
CREATE TABLE candidate (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 text        NOT NULL,
    email                citext      NOT NULL UNIQUE,   -- without citext: use text + unique index on lower(email)
    phone                text,
    consent_talent_bank  boolean     NOT NULL DEFAULT false,  -- PDPA: consent to keep data in the talent bank
    created_at           timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- job — a position/programme (e.g. RISE@MCMC); requirements holds scoring rules
-- ---------------------------------------------------------------------------
CREATE TABLE job (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title         text        NOT NULL,
    description   text,
    -- Scoring rules, e.g.:
    -- { "knockout": { "min_cgpa": 3.20, "fields": ["CS","SE","IS","IT","Data Science"],
    --                 "require_fulltime": true, "langs_any": ["Python","PHP"], "require_sql": true },
    --   "bonus":    { "ai_study": 10, "eca": 8, "extra_lang": 5 } }
    requirements  jsonb       NOT NULL DEFAULT '{}'::jsonb,
    is_open       boolean     NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- application — one application (candidate × job)
-- Structured columns are the primary source for knockout checks;
-- form_data keeps the complete raw form submission
-- ---------------------------------------------------------------------------
CREATE TABLE application (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id    uuid NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,
    job_id          uuid NOT NULL REFERENCES job(id)       ON DELETE RESTRICT,
    cgpa            numeric(3,2),                 -- 0.00 - 4.00
    degree_field    text,
    is_fulltime     boolean,
    prog_langs      text[]      NOT NULL DEFAULT '{}',   -- e.g. {Python,PHP,Java}
    has_sql         boolean     NOT NULL DEFAULT false,
    has_ai_study    boolean     NOT NULL DEFAULT false,
    eca             text,                                 -- extra-curricular activities
    resume_file_url text,                                 -- resume lives in object storage; only the key is stored here
    form_data       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    status          application_status NOT NULL DEFAULT 'applied',
    -- When the application entered the shortlist;
    -- expiry = shortlisted_at + app_setting.shortlist_review_days
    shortlisted_at  timestamptz,
    -- Rejection reason: auto_no_review (review timeout) / low_band / manual, etc.
    rejected_reason text,
    submitted_at    timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    -- One application per candidate per job
    UNIQUE (candidate_id, job_id)
);
CREATE INDEX idx_application_status ON application(status);
CREATE INDEX idx_application_job    ON application(job_id);
-- Scheduled job scans applications stuck in shortlist, then applies the
-- configured expiry window
CREATE INDEX idx_application_shortlisted_at
    ON application(shortlisted_at) WHERE status = 'shortlisted';

-- ---------------------------------------------------------------------------
-- score — scoring result (one row per application)
-- ---------------------------------------------------------------------------
CREATE TABLE score (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id   uuid NOT NULL UNIQUE REFERENCES application(id) ON DELETE CASCADE,
    knockout_passed  boolean     NOT NULL,         -- all hard requirements met?
    band             score_band  NOT NULL,         -- high / medium / low
    total_score      numeric(6,2),
    breakdown        jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- per-item score detail
    reasoning        text,                          -- explainable reasoning (PDPA/fairness)
    model            text,                          -- which model produced it
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- interviewer
-- ---------------------------------------------------------------------------
CREATE TABLE interviewer (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name       text   NOT NULL,
    email      citext NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- slot — a fixed one-hour time cell
-- Panel mode: up to 5 interviewers + exactly 1 candidate
-- ---------------------------------------------------------------------------
CREATE TABLE slot (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slot_date    date        NOT NULL,
    start_time   time        NOT NULL,
    end_time     time        NOT NULL,
    candidate_id uuid        REFERENCES candidate(id) ON DELETE SET NULL,  -- set when booked
    status       slot_status NOT NULL DEFAULT 'empty',
    created_at   timestamptz NOT NULL DEFAULT now(),
    -- Only one cell per date + start time
    UNIQUE (slot_date, start_time),
    CHECK (end_time > start_time)
);
-- A candidate holds at most one slot (withdrawing clears it so they can pick again)
CREATE UNIQUE INDEX uq_slot_one_per_candidate
    ON slot(candidate_id) WHERE candidate_id IS NOT NULL;
CREATE INDEX idx_slot_open ON slot(slot_date) WHERE status = 'open';

-- ---------------------------------------------------------------------------
-- slot_interviewer — interviewers claiming slots (many-to-many)
-- ---------------------------------------------------------------------------
CREATE TABLE slot_interviewer (
    slot_id        uuid NOT NULL REFERENCES slot(id)        ON DELETE CASCADE,
    interviewer_id uuid NOT NULL REFERENCES interviewer(id) ON DELETE CASCADE,
    claimed_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (slot_id, interviewer_id)
);
CREATE INDEX idx_slot_interviewer_interviewer ON slot_interviewer(interviewer_id);

-- Panel cap: before insert, check the slot's claimed-interviewer count
CREATE OR REPLACE FUNCTION check_panel_capacity() RETURNS trigger AS $$
DECLARE
    cap int;
BEGIN
    SELECT (value #>> '{}')::int INTO cap
        FROM app_setting WHERE key = 'panel_max_interviewers';
    cap := COALESCE(cap, 5);
    IF (SELECT count(*) FROM slot_interviewer WHERE slot_id = NEW.slot_id) >= cap THEN
        RAISE EXCEPTION 'slot % already has % interviewers (panel cap)', NEW.slot_id, cap;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_panel_capacity
    BEFORE INSERT ON slot_interviewer
    FOR EACH ROW EXECUTE FUNCTION check_panel_capacity();

-- A booked slot must never drop to zero interviewers: reject the withdrawal
-- if the slot is booked and this is the last panel member
CREATE OR REPLACE FUNCTION guard_booked_min_interviewer() RETURNS trigger AS $$
DECLARE
    s_status slot_status;
    remaining int;
BEGIN
    SELECT status INTO s_status FROM slot WHERE id = OLD.slot_id;
    SELECT count(*) INTO remaining FROM slot_interviewer
        WHERE slot_id = OLD.slot_id AND interviewer_id <> OLD.interviewer_id;
    IF s_status = 'booked' AND remaining = 0 THEN
        RAISE EXCEPTION 'cannot remove last interviewer from a booked slot; cancel the interview first';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_booked_min_interviewer
    BEFORE DELETE ON slot_interviewer
    FOR EACH ROW EXECUTE FUNCTION guard_booked_min_interviewer();

-- ---------------------------------------------------------------------------
-- interview — one interview (application × slot)
-- ---------------------------------------------------------------------------
CREATE TABLE interview (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id   uuid NOT NULL REFERENCES application(id) ON DELETE CASCADE,
    slot_id          uuid NOT NULL REFERENCES slot(id)        ON DELETE RESTRICT,
    meeting_link     text,                                    -- online meeting link
    status           interview_status NOT NULL DEFAULT 'scheduled',
    reschedule_count int         NOT NULL DEFAULT 0,
    confirmed_at     timestamptz,                             -- when the candidate confirmed the booking
    created_at       timestamptz NOT NULL DEFAULT now()
);
-- An application can only have one active interview at a time
CREATE UNIQUE INDEX uq_one_active_interview
    ON interview(application_id) WHERE status = 'scheduled';
CREATE INDEX idx_interview_slot ON interview(slot_id);

-- ---------------------------------------------------------------------------
-- email_log — email drafts and send records (drafted first, sent after review)
-- ---------------------------------------------------------------------------
CREATE TABLE email_log (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL REFERENCES application(id) ON DELETE CASCADE,
    type           email_type   NOT NULL,
    subject        text         NOT NULL,
    body           text         NOT NULL,
    status         email_status NOT NULL DEFAULT 'draft',
    created_at     timestamptz  NOT NULL DEFAULT now(),
    sent_at        timestamptz
);
CREATE INDEX idx_email_application ON email_log(application_id);

-- ============================================================================
-- Optional: talent-bank semantic search (RAG usage)
-- Uncomment after enabling pgvector. Set the dimension to match the chosen
-- embedding model.
-- ============================================================================
-- CREATE TABLE candidate_resume_embedding (
--     candidate_id uuid PRIMARY KEY REFERENCES candidate(id) ON DELETE CASCADE,
--     chunk_text   text,
--     embedding    vector(1024),
--     created_at   timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE INDEX idx_resume_embedding ON candidate_resume_embedding
--     USING hnsw (embedding vector_cosine_ops);
