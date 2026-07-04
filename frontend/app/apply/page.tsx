"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

type JobOpt = { id: string; title: string };

const DEGREE_FIELDS = ["CS", "SE", "IS", "IT", "Data Science", "Other"];
const LANGS = ["Python", "PHP", "Java", "JavaScript", "C++", "Go"];

export default function ApplyPage() {
  const [jobs, setJobs] = useState<JobOpt[]>([]);
  const [form, setForm] = useState({
    job_id: "",
    name: "",
    email: "",
    phone: "",
    cgpa: "",
    degree_field: "CS",
    is_fulltime: true,
    prog_langs: [] as string[],
    has_sql: false,
    has_ai_study: false,
    eca: "",
    consent_talent_bank: false,
  });
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resume, setResume] = useState<File | null>(null);

  useEffect(() => {
    fetch(`${API}/api/jobs`)
      .then((r) => r.json())
      .then((list: JobOpt[]) => {
        setJobs(list);
        if (list.length) setForm((f) => ({ ...f, job_id: list[0].id }));
      })
      .catch((e) => setError(String(e)));
  }, []);

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("job_id", form.job_id);
      fd.append("name", form.name);
      fd.append("email", form.email);
      if (form.phone) fd.append("phone", form.phone);
      fd.append("cgpa", form.cgpa);
      fd.append("degree_field", form.degree_field);
      fd.append("is_fulltime", String(form.is_fulltime));
      fd.append("prog_langs", JSON.stringify(form.prog_langs));
      fd.append("has_sql", String(form.has_sql));
      fd.append("has_ai_study", String(form.has_ai_study));
      if (form.eca) fd.append("eca", form.eca);
      fd.append("consent_talent_bank", String(form.consent_talent_bank));
      if (resume) fd.append("resume", resume);

      const r = await fetch(`${API}/api/applications`, { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok) {
        const detail = Array.isArray(data.detail)
          ? data.detail.map((d: { msg: string }) => d.msg).join("; ")
          : data.detail;
        throw new Error(detail ?? `HTTP ${r.status}`);
      }
      setResult(data.message);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <main style={wrap}>
        <h1>Thank you!</h1>
        <p>{result}</p>
      </main>
    );
  }

  return (
    <main style={wrap}>
      <h1>Internship application</h1>
      {error && <p style={{ color: "#b00" }}>{error}</p>}

      <label style={lbl}>Position</label>
      <select style={input} value={form.job_id} onChange={(e) => set("job_id", e.target.value)}>
        {jobs.map((j) => (
          <option key={j.id} value={j.id}>{j.title}</option>
        ))}
      </select>

      <label style={lbl}>Full name *</label>
      <input style={input} value={form.name} onChange={(e) => set("name", e.target.value)} />

      <label style={lbl}>Email *</label>
      <input style={input} type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />

      <label style={lbl}>Phone</label>
      <input style={input} value={form.phone} onChange={(e) => set("phone", e.target.value)} />

      <label style={lbl}>CGPA (0.00 – 4.00) *</label>
      <input style={input} type="number" step="0.01" min="0" max="4" value={form.cgpa}
        onChange={(e) => set("cgpa", e.target.value)} />

      <label style={lbl}>Degree field *</label>
      <select style={input} value={form.degree_field} onChange={(e) => set("degree_field", e.target.value)}>
        {DEGREE_FIELDS.map((d) => <option key={d}>{d}</option>)}
      </select>

      <label style={chk}>
        <input type="checkbox" checked={form.is_fulltime}
          onChange={(e) => set("is_fulltime", e.target.checked)} /> Full-time student
      </label>

      <label style={lbl}>Programming languages</label>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        {LANGS.map((l) => (
          <label key={l} style={chk}>
            <input
              type="checkbox"
              checked={form.prog_langs.includes(l)}
              onChange={(e) =>
                set(
                  "prog_langs",
                  e.target.checked
                    ? [...form.prog_langs, l]
                    : form.prog_langs.filter((x) => x !== l)
                )
              }
            /> {l}
          </label>
        ))}
      </div>

      <label style={chk}>
        <input type="checkbox" checked={form.has_sql}
          onChange={(e) => set("has_sql", e.target.checked)} /> I know SQL
      </label>
      <label style={chk}>
        <input type="checkbox" checked={form.has_ai_study}
          onChange={(e) => set("has_ai_study", e.target.checked)} /> I have studied AI (courses/projects)
      </label>

      <label style={lbl}>Resume(PDF / DOCX / TXT,≤5MB)</label>
      <input
        style={{ ...input, padding: "6px" }}
        type="file"
        accept=".pdf,.docx,.txt"
        onChange={(e) => setResume(e.target.files?.[0] ?? null)}
      />

      <label style={lbl}>Extra-curricular activities</label>
      <textarea style={{ ...input, height: 80 }} value={form.eca}
        onChange={(e) => set("eca", e.target.value)} />

      <label style={chk}>
        <input type="checkbox" checked={form.consent_talent_bank}
          onChange={(e) => set("consent_talent_bank", e.target.checked)} />{" "}
        I consent to my data being kept in the talent bank for future opportunities
      </label>

      <p>
        <button
          style={primary}
          disabled={busy || !form.job_id || !form.name || !form.email || !form.cgpa}
          onClick={submit}
        >
          {busy ? "Submitting…" : "Submit application"}
        </button>
      </p>
    </main>
  );
}

const wrap: React.CSSProperties = { maxWidth: 560, margin: "0 auto" };
const lbl: React.CSSProperties = { display: "block", marginTop: 14, fontWeight: 600 };
const input: React.CSSProperties = {
  display: "block", width: "100%", padding: "8px 10px", marginTop: 4,
  border: "1px solid #ccc", borderRadius: 6, boxSizing: "border-box",
};
const chk: React.CSSProperties = { display: "block", marginTop: 10 };
const primary: React.CSSProperties = {
  padding: "10px 22px", border: "none", borderRadius: 6,
  background: "#334", color: "#fff", cursor: "pointer",
};
