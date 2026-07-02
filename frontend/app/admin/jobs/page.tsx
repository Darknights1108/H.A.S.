"use client";

import { useCallback, useEffect, useState } from "react";

import AdminBar from "@/components/AdminBar";
import { useSession } from "@/lib/session";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

type JobRow = {
  id: string; title: string; description: string | null;
  requirements: Requirements; is_open: boolean; created_at: string;
};
type Requirements = {
  knockout?: {
    min_cgpa?: number; fields?: string[]; require_fulltime?: boolean;
    langs_any?: string[]; require_sql?: boolean;
  };
  bonus?: { ai_study?: number; eca?: number; extra_lang?: number };
  high_min_bonus?: number;
};

const emptyDraft = {
  title: "",
  description: "",
  min_cgpa: "",
  fields: "",
  require_fulltime: false,
  langs_any: "",
  require_sql: false,
  ai_study: "10",
  eca: "8",
  extra_lang: "5",
  high_min_bonus: "15",
};

export default function AdminJobsPage() {
  const { session, loading: authLoading } = useSession(true);
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [jdText, setJdText] = useState("");
  const [draft, setDraft] = useState(emptyDraft);
  const [unmapped, setUnmapped] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch(`${API}/api/jobs/all`);
    if (r.ok) setJobs(await r.json());
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function set<K extends keyof typeof draft>(k: K, v: (typeof draft)[K]) {
    setDraft((d) => ({ ...d, [k]: v }));
  }

  async function parseJd() {
    setBusy(true);
    setNotice(null);
    setUnmapped([]);
    try {
      const r = await fetch(`${API}/api/jobs/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: jdText }),
      });
      const data = await r.json();
      if (!r.ok) {
        setNotice(data.detail ?? `HTTP ${r.status}`);
        setShowForm(true); // 降级:无 key 时直接开手动表单
        return;
      }
      const ko = data.requirements.knockout ?? {};
      const bo = data.requirements.bonus ?? {};
      setDraft({
        title: data.title ?? "",
        description: data.description ?? "",
        min_cgpa: ko.min_cgpa != null ? String(ko.min_cgpa) : "",
        fields: (ko.fields ?? []).join(", "),
        require_fulltime: !!ko.require_fulltime,
        langs_any: (ko.langs_any ?? []).join(", "),
        require_sql: !!ko.require_sql,
        ai_study: bo.ai_study != null ? String(bo.ai_study) : "",
        eca: bo.eca != null ? String(bo.eca) : "",
        extra_lang: bo.extra_lang != null ? String(bo.extra_lang) : "",
        high_min_bonus: String(data.requirements.high_min_bonus ?? 15),
      });
      setUnmapped(data.unmapped ?? []);
      setShowForm(true);
      setNotice(`AI 解析完成(${data.model})— 请检查下方规则,可修改后创建`);
    } catch (e) {
      setNotice(String(e));
    } finally {
      setBusy(false);
    }
  }

  function buildRequirements(): Requirements {
    const knockout: Requirements["knockout"] = {};
    if (draft.min_cgpa) knockout.min_cgpa = parseFloat(draft.min_cgpa);
    if (draft.fields.trim())
      knockout.fields = draft.fields.split(",").map((s) => s.trim()).filter(Boolean);
    if (draft.require_fulltime) knockout.require_fulltime = true;
    if (draft.langs_any.trim())
      knockout.langs_any = draft.langs_any.split(",").map((s) => s.trim()).filter(Boolean);
    if (draft.require_sql) knockout.require_sql = true;
    const bonus: Requirements["bonus"] = {};
    if (draft.ai_study) bonus.ai_study = parseFloat(draft.ai_study);
    if (draft.eca) bonus.eca = parseFloat(draft.eca);
    if (draft.extra_lang) bonus.extra_lang = parseFloat(draft.extra_lang);
    return { knockout, bonus, high_min_bonus: parseFloat(draft.high_min_bonus || "15") };
  }

  async function createJob() {
    setBusy(true);
    setNotice(null);
    try {
      const r = await fetch(`${API}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: draft.title,
          description: draft.description || null,
          requirements: buildRequirements(),
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail ?? `HTTP ${r.status}`);
      setNotice(`职位已创建:${data.title}`);
      setDraft(emptyDraft);
      setJdText("");
      setShowForm(false);
      setUnmapped([]);
      await load();
    } catch (e) {
      setNotice(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggleOpen(job: JobRow) {
    await fetch(`${API}/api/jobs/${job.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_open: !job.is_open }),
    });
    await load();
  }

  if (authLoading || !session) return <main><p>Loading…</p></main>;

  return (
    <main style={{ maxWidth: 860 }}>
      <AdminBar session={session} />
      <h1>Jobs admin</h1>

      <section style={card}>
        <h2 style={{ marginTop: 0 }}>New job — paste the JD</h2>
        <textarea
          style={{ ...input, height: 160, fontFamily: "inherit" }}
          placeholder="把职位描述(JD)原文贴在这里,AI 会解析出筛选规则……"
          value={jdText}
          onChange={(e) => setJdText(e.target.value)}
        />
        <p>
          <button style={primary} disabled={busy || jdText.trim().length < 20} onClick={parseJd}>
            {busy ? "Parsing…" : "Parse with AI"}
          </button>{" "}
          <button style={secondary} disabled={busy} onClick={() => setShowForm(true)}>
            Fill rules manually
          </button>
        </p>
        {notice && <p style={{ color: notice.includes("失败") || notice.includes("HTTP") || notice.includes("not configured") ? "#b00" : "#06c" }}>{notice}</p>}
        {unmapped.length > 0 && (
          <div style={{ background: "#fff8e1", border: "1px solid #f0d264", borderRadius: 6, padding: "8px 12px" }}>
            <b>无法映射到表单的要求(需人工留意):</b>
            <ul style={{ margin: "4px 0" }}>
              {unmapped.map((u, i) => <li key={i}>{u}</li>)}
            </ul>
          </div>
        )}
      </section>

      {showForm && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Screening rules(可修改)</h2>
          <label style={lbl}>Title *</label>
          <input style={input} value={draft.title} onChange={(e) => set("title", e.target.value)} />
          <label style={lbl}>Description</label>
          <textarea style={{ ...input, height: 60 }} value={draft.description}
            onChange={(e) => set("description", e.target.value)} />

          <h3>Knockout(硬门槛,留空 = 不检查该项)</h3>
          <label style={lbl}>Min CGPA</label>
          <input style={input} type="number" step="0.01" value={draft.min_cgpa}
            onChange={(e) => set("min_cgpa", e.target.value)} />
          <label style={lbl}>Accepted degree fields(逗号分隔,如 CS, SE, IT)</label>
          <input style={input} value={draft.fields} onChange={(e) => set("fields", e.target.value)} />
          <label style={chk}>
            <input type="checkbox" checked={draft.require_fulltime}
              onChange={(e) => set("require_fulltime", e.target.checked)} /> Require full-time student
          </label>
          <label style={lbl}>Required languages — any of(逗号分隔,如 Python, PHP)</label>
          <input style={input} value={draft.langs_any} onChange={(e) => set("langs_any", e.target.value)} />
          <label style={chk}>
            <input type="checkbox" checked={draft.require_sql}
              onChange={(e) => set("require_sql", e.target.checked)} /> Require SQL
          </label>

          <h3>Bonus(加分,留空 = 不加分)</h3>
          <label style={lbl}>AI study points</label>
          <input style={input} type="number" value={draft.ai_study} onChange={(e) => set("ai_study", e.target.value)} />
          <label style={lbl}>Extra-curricular points</label>
          <input style={input} type="number" value={draft.eca} onChange={(e) => set("eca", e.target.value)} />
          <label style={lbl}>Extra language points</label>
          <input style={input} type="number" value={draft.extra_lang} onChange={(e) => set("extra_lang", e.target.value)} />
          <label style={lbl}>High band threshold(bonus ≥ 此值 → High)</label>
          <input style={input} type="number" value={draft.high_min_bonus}
            onChange={(e) => set("high_min_bonus", e.target.value)} />

          <p>
            <button style={primary} disabled={busy || !draft.title} onClick={createJob}>
              Create job
            </button>
          </p>
        </section>
      )}

      <section style={card}>
        <h2 style={{ marginTop: 0 }}>Existing jobs</h2>
        {jobs.map((j) => (
          <div key={j.id} style={{ borderBottom: "1px solid #eee", padding: "8px 0" }}>
            <b>{j.title}</b>{" "}
            <span style={{ ...badge, background: j.is_open ? "#d8f5e8" : "#eee", color: j.is_open ? "#0a6" : "#777" }}>
              {j.is_open ? "open" : "closed"}
            </span>{" "}
            <button style={btnSm} onClick={() => toggleOpen(j)}>
              {j.is_open ? "Close" : "Reopen"}
            </button>
            <pre style={{ fontSize: 12, color: "#666", whiteSpace: "pre-wrap", margin: "6px 0 0" }}>
              {JSON.stringify(j.requirements, null, 1)}
            </pre>
          </div>
        ))}
      </section>
    </main>
  );
}

const card: React.CSSProperties = {
  border: "1px solid #ddd", borderRadius: 8, padding: "12px 16px", margin: "16px 0",
};
const lbl: React.CSSProperties = { display: "block", marginTop: 10, fontWeight: 600 };
const chk: React.CSSProperties = { display: "block", marginTop: 10 };
const input: React.CSSProperties = {
  display: "block", width: "100%", padding: "8px 10px", marginTop: 4,
  border: "1px solid #ccc", borderRadius: 6, boxSizing: "border-box",
};
const primary: React.CSSProperties = {
  padding: "10px 20px", border: "none", borderRadius: 6, background: "#334", color: "#fff", cursor: "pointer",
};
const secondary: React.CSSProperties = {
  padding: "10px 20px", border: "1px solid #ccc", borderRadius: 6, background: "#f5f5f5", cursor: "pointer",
};
const btnSm: React.CSSProperties = {
  padding: "3px 10px", border: "none", borderRadius: 4, background: "#334", color: "#fff", cursor: "pointer", fontSize: 12,
};
const badge: React.CSSProperties = { padding: "2px 10px", borderRadius: 10, fontSize: 12 };
