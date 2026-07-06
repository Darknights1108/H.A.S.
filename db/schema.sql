-- ============================================================================
-- Hiring Automation System (HAS) — PostgreSQL schema
-- Target: PostgreSQL 14+
-- 约定:UUID 主键 (gen_random_uuid)、时间统一 timestamptz、时区在应用层固定 MYT
-- ============================================================================

-- gen_random_uuid() 来自 pgcrypto(PG13+ 内置);citext 用于大小写不敏感 email
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
-- CREATE EXTENSION IF NOT EXISTS vector;   -- 需要语义搜索时再开启(见文件末尾)

-- ---------------------------------------------------------------------------
-- 枚举类型
-- ---------------------------------------------------------------------------
CREATE TYPE application_status AS ENUM (
    'applied',       -- 新申请
    'scored',        -- 已自动打分
    'shortlisted',   -- admin 复核后入选
    'scheduled',     -- 已约面试
    'interviewed',   -- 已面试
    'passed',        -- 通过
    'rejected'       -- 婉拒
);

CREATE TYPE score_band     AS ENUM ('high', 'medium', 'low');
CREATE TYPE slot_status    AS ENUM ('empty', 'open', 'booked');
CREATE TYPE interview_status AS ENUM ('scheduled', 'completed', 'passed', 'failed', 'cancelled');
CREATE TYPE email_type     AS ENUM ('invite', 'offer', 'reject');
CREATE TYPE email_status   AS ENUM ('draft', 'sent');

-- ---------------------------------------------------------------------------
-- app_setting — 全局可配置项(admin 在 settings 页面改;通用 key-value,加配置不改表)
-- ---------------------------------------------------------------------------
CREATE TABLE app_setting (
    key         text PRIMARY KEY,
    value       jsonb       NOT NULL,
    description text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- 默认值(seed)
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
    ('invite_email_template', '"Hi {candidate_name},\n\nCongratulations! You have been shortlisted for {job_title}.\n\nPlease pick an interview time that suits you using your personal booking link:\n{booking_url}\n\nAll interviews are conducted online (times in MYT, UTC+08:00).\n\nBest Regards,\n{company_name} Recruiting Team\n"', 'Invite email body template. Placeholders: {candidate_name} {job_title} {booking_url} {company_name}')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- candidate — 去重的人(同一 email 视为同一人)
-- ---------------------------------------------------------------------------
CREATE TABLE candidate (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 text        NOT NULL,
    email                citext      NOT NULL UNIQUE,   -- 需要 citext 扩展则改 text + lower 唯一索引
    phone                text,
    consent_talent_bank  boolean     NOT NULL DEFAULT false,  -- PDPA:同意存入人才库
    created_at           timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- job — 职位/项目(如 RISE@MCMC),requirements 存评分规则配置
-- ---------------------------------------------------------------------------
CREATE TABLE job (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title         text        NOT NULL,
    description   text,
    -- 评分规则,例如:
    -- { "knockout": { "min_cgpa": 3.20, "fields": ["CS","SE","IS","IT","Data Science"],
    --                 "require_fulltime": true, "langs_any": ["Python","PHP"], "require_sql": true },
    --   "bonus":    { "ai_study": 10, "eca": 8, "extra_lang": 5 } }
    requirements  jsonb       NOT NULL DEFAULT '{}'::jsonb,
    is_open       boolean     NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- application — 一次申请(候选人 × 职位)
-- 结构化字段为硬门槛判断的主数据源;form_data 存完整原始表单
-- ---------------------------------------------------------------------------
CREATE TABLE application (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id    uuid NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,
    job_id          uuid NOT NULL REFERENCES job(id)       ON DELETE RESTRICT,
    cgpa            numeric(3,2),                 -- 0.00 - 4.00
    degree_field    text,
    is_fulltime     boolean,
    prog_langs      text[]      NOT NULL DEFAULT '{}',   -- 例:{Python,PHP,Java}
    has_sql         boolean     NOT NULL DEFAULT false,
    has_ai_study    boolean     NOT NULL DEFAULT false,
    eca             text,                                 -- 课外活动描述
    resume_file_url text,                                 -- 原始简历存对象存储,这里只放 URL
    form_data       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    status          application_status NOT NULL DEFAULT 'applied',
    -- 进入 shortlist 的时间;过期判断 = shortlisted_at + app_setting.shortlist_review_days
    shortlisted_at  timestamptz,
    -- 淘汰原因:auto_no_review(超时无人审) / low_band / manual 等
    rejected_reason text,
    submitted_at    timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    -- 同一候选人对同一职位只允许一份申请
    UNIQUE (candidate_id, job_id)
);
CREATE INDEX idx_application_status ON application(status);
CREATE INDEX idx_application_job    ON application(job_id);
-- 定时任务扫描"卡在 shortlist"的申请,再按配置天数算是否过期
CREATE INDEX idx_application_shortlisted_at
    ON application(shortlisted_at) WHERE status = 'shortlisted';

-- ---------------------------------------------------------------------------
-- score — 打分结果(每份 application 一条)
-- ---------------------------------------------------------------------------
CREATE TABLE score (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id   uuid NOT NULL UNIQUE REFERENCES application(id) ON DELETE CASCADE,
    knockout_passed  boolean     NOT NULL,         -- 硬门槛是否全过
    band             score_band  NOT NULL,         -- high / medium / low
    total_score      numeric(6,2),
    breakdown        jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- 各项得分明细
    reasoning        text,                          -- 可解释理由(PDPA/公平性)
    model            text,                          -- 用了哪个模型
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- interviewer — 面试官
-- ---------------------------------------------------------------------------
CREATE TABLE interviewer (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name       text   NOT NULL,
    email      citext NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- slot — 时间格子(固定 1 小时一格)
-- Panel 模式:最多 5 位面试官 + 恰好 1 个候选人
-- ---------------------------------------------------------------------------
CREATE TABLE slot (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slot_date    date        NOT NULL,
    start_time   time        NOT NULL,
    end_time     time        NOT NULL,
    candidate_id uuid        REFERENCES candidate(id) ON DELETE SET NULL,  -- 被订时填
    status       slot_status NOT NULL DEFAULT 'empty',
    created_at   timestamptz NOT NULL DEFAULT now(),
    -- 同一天同一开始时间只有一格
    UNIQUE (slot_date, start_time),
    CHECK (end_time > start_time)
);
-- 一个候选人名下最多占一个时段(撤回后置空即可再选)
CREATE UNIQUE INDEX uq_slot_one_per_candidate
    ON slot(candidate_id) WHERE candidate_id IS NOT NULL;
CREATE INDEX idx_slot_open ON slot(slot_date) WHERE status = 'open';

-- ---------------------------------------------------------------------------
-- slot_interviewer — 面试官认领时段(多对多)
-- ---------------------------------------------------------------------------
CREATE TABLE slot_interviewer (
    slot_id        uuid NOT NULL REFERENCES slot(id)        ON DELETE CASCADE,
    interviewer_id uuid NOT NULL REFERENCES interviewer(id) ON DELETE CASCADE,
    claimed_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (slot_id, interviewer_id)
);
CREATE INDEX idx_slot_interviewer_interviewer ON slot_interviewer(interviewer_id);

-- panel 上限 5:写入前检查该 slot 已认领面试官数 < 5
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

-- 已被预订(booked)的时段,不能退到 0 面试官:撤回时若该 slot 已 booked 且这是最后一位,拒绝
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
-- interview — 一场面试(application × slot)
-- ---------------------------------------------------------------------------
CREATE TABLE interview (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id   uuid NOT NULL REFERENCES application(id) ON DELETE CASCADE,
    slot_id          uuid NOT NULL REFERENCES slot(id)        ON DELETE RESTRICT,
    meeting_link     text,                                    -- online 会议链接
    status           interview_status NOT NULL DEFAULT 'scheduled',
    reschedule_count int         NOT NULL DEFAULT 0,
    confirmed_at     timestamptz,                             -- 候选人点"确认"后发邀请的时间
    created_at       timestamptz NOT NULL DEFAULT now()
);
-- 一份申请同时只能有一场进行中的面试(撤回改选 / 一人一档)
CREATE UNIQUE INDEX uq_one_active_interview
    ON interview(application_id) WHERE status = 'scheduled';
CREATE INDEX idx_interview_slot ON interview(slot_id);

-- ---------------------------------------------------------------------------
-- email_log — 邮件草稿与发送记录(草稿先生成,admin 复核后发送)
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
-- 可选:talent bank 语义搜索(RAG 用法)
-- 启用 pgvector 后取消注释。维度按所选 embedding 模型设定。
-- ============================================================================
-- CREATE TABLE candidate_resume_embedding (
--     candidate_id uuid PRIMARY KEY REFERENCES candidate(id) ON DELETE CASCADE,
--     chunk_text   text,
--     embedding    vector(1024),
--     created_at   timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE INDEX idx_resume_embedding ON candidate_resume_embedding
--     USING hnsw (embedding vector_cosine_ops);
