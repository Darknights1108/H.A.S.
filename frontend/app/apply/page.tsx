"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

type JobOpt = { id: string; title: string; description: string | null };

const DEGREE_FIELDS = [
  "Computer Science", "Software Engineering", "Information Technology",
  "Information Systems", "Data Science", "Engineering", "Business",
  "Accounting", "Finance", "Marketing", "Human Resources", "Design",
  "Science", "Education", "Healthcare", "Law", "Other",
];
const EDU_LEVELS = [
  "Diploma", "Bachelor's Degree", "Master's Degree", "PhD",
  "Professional Certificate", "Other",
];
const SOURCES = ["LinkedIn", "JobStreet", "University / Career fair", "Friend or referral", "Company website", "Other"];

const SECTIONS: [string, string][] = [
  ["position", "Position"],
  ["resume", "Resume"],
  ["contact", "Contact Information"],
  ["academic", "Academic Background"],
  ["additional", "Additional Information"],
  ["consent", "Consent & Submit"],
];

export default function ApplyPage() {
  const [jobs, setJobs] = useState<JobOpt[]>([]);
  const [form, setForm] = useState({
    job_id: "",
    name: "",
    email: "",
    phone: "",
    education_level: "Bachelor's Degree",
    degree_field: "Computer Science",
    institution: "",
    cgpa: "",
    is_fulltime: true,
    eca: "",
    consent_talent_bank: false,
    preferred_start_date: "",
    salary_expectation: "",
    heard_about_us: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resume, setResume] = useState<File | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [detected, setDetected] = useState<number | null>(null);

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

  const selectedJob = jobs.find((j) => j.id === form.job_id);

  // 选中简历后立即 AI 提取技能,暂存给下一步 Skill Assessment 页
  async function onResumePicked(file: File | null) {
    setResume(file);
    setDetected(null);
    sessionStorage.removeItem("has_resume_skills");
    if (!file) return;
    setSuggesting(true);
    try {
      const fd = new FormData();
      fd.append("resume", file);
      const r = await fetch(`${API}/api/resume/skill-suggest`, { method: "POST", body: fd });
      if (r.ok) {
        const data = await r.json();
        sessionStorage.setItem("has_resume_skills", JSON.stringify(data.skills ?? []));
        setDetected((data.skills ?? []).length);
      }
    } catch {
      /* best-effort */
    } finally {
      setSuggesting(false);
    }
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
      fd.append("education_level", form.education_level);
      if (form.institution) fd.append("institution", form.institution);
      if (form.eca) fd.append("eca", form.eca);
      fd.append("consent_talent_bank", String(form.consent_talent_bank));
      if (form.preferred_start_date) fd.append("preferred_start_date", form.preferred_start_date);
      if (form.salary_expectation) fd.append("salary_expectation", form.salary_expectation);
      if (form.heard_about_us) fd.append("heard_about_us", form.heard_about_us);
      if (resume) fd.append("resume", resume);

      const r = await fetch(`${API}/api/applications`, { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok) {
        const detail = Array.isArray(data.detail)
          ? data.detail.map((d: { msg: string }) => d.msg).join("; ")
          : data.detail;
        throw new Error(detail ?? `HTTP ${r.status}`);
      }
      // 进入第二步:Skill Assessment
      window.location.href = `/apply/skills?token=${data.skill_token}`;
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 980, margin: "0 auto" }}>
      <h1>Application for</h1>
      <div style={jobHeader}>
        <span style={jobIcon}>💼</span>
        <div>
          <div style={{ fontWeight: 600, fontSize: 17 }}>
            {selectedJob?.title ?? "—"}
          </div>
          <div style={{ color: "#6b7280", fontSize: 13 }}>Online interview · MYT (UTC+08:00)</div>
        </div>
      </div>
      <p style={{ color: "#6b7280", fontSize: 13 }}>
        Required fields are indicated with <span style={{ color: "#dc2626" }}>*</span>
        {" · "}After submitting you will be asked to confirm your skills.
      </p>
      {error && <p style={{ color: "#dc2626" }}>{error}</p>}

      <div style={{ display: "flex", gap: 28, alignItems: "flex-start" }}>
        <nav style={sideNav}>
          {SECTIONS.map(([id, label]) => (
            <a key={id} href={`#${id}`} style={navItem}>
              <span style={navDot} />
              {label}
            </a>
          ))}
          <span style={{ ...navItem, color: "#9ca3af" }}>
            <span style={{ ...navDot, borderColor: "#d1d5db" }} />
            Skill Assessment (next step)
          </span>
        </nav>

        <div style={{ flex: 1, minWidth: 320 }}>
          <section id="position" style={card}>
            <h2 style={h2}>Position</h2>
            <label style={lbl}>Select the position you want to apply for <Req /></label>
            <select style={input} value={form.job_id} onChange={(e) => set("job_id", e.target.value)}>
              {jobs.map((j) => (
                <option key={j.id} value={j.id}>{j.title}</option>
              ))}
            </select>
            {selectedJob?.description && (
              <p style={{ color: "#6b7280", fontSize: 13, marginBottom: 0 }}>{selectedJob.description}</p>
            )}
          </section>

          <section id="resume" style={card}>
            <h2 style={h2}>Resume</h2>
            <label style={lbl}>Upload your resume (PDF / DOCX / TXT, max 5MB)</label>
            <input
              style={{ ...input, padding: 6 }}
              type="file"
              accept=".pdf,.docx,.txt"
              onChange={(e) => onResumePicked(e.target.files?.[0] ?? null)}
            />
            {resume && (
              <p style={{ color: "#059669", fontSize: 13, marginBottom: 0 }}>✓ {resume.name}</p>
            )}
            {suggesting && (
              <p style={{ color: "#6b7280", fontSize: 13, marginBottom: 0 }}>
                Analyzing resume for skills…
              </p>
            )}
            {detected != null && !suggesting && (
              <p style={{ color: "#6b7280", fontSize: 13, marginBottom: 0 }}>
                {detected} skills detected — you can confirm them in the next step.
              </p>
            )}
          </section>

          <section id="contact" style={card}>
            <h2 style={h2}>Contact Information</h2>
            <label style={lbl}>Full name <Req /></label>
            <input style={input} value={form.name} onChange={(e) => set("name", e.target.value)} />
            <label style={lbl}>Email <Req /></label>
            <input style={input} type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
            <label style={lbl}>Phone</label>
            <input style={input} placeholder="+60…" value={form.phone} onChange={(e) => set("phone", e.target.value)} />
          </section>

          <section id="academic" style={card}>
            <h2 style={h2}>Academic Background</h2>
            <label style={lbl}>Education level <Req /></label>
            <select style={input} value={form.education_level}
              onChange={(e) => set("education_level", e.target.value)}>
              {EDU_LEVELS.map((x) => <option key={x}>{x}</option>)}
            </select>
            <label style={lbl}>Field of study <Req /></label>
            <select style={input} value={form.degree_field} onChange={(e) => set("degree_field", e.target.value)}>
              {DEGREE_FIELDS.map((d) => <option key={d}>{d}</option>)}
            </select>
            <label style={lbl}>Institution</label>
            <input style={input} placeholder="e.g. Universiti Malaya" value={form.institution}
              onChange={(e) => set("institution", e.target.value)} />
            <label style={lbl}>CGPA (0.00 – 4.00) <Req /></label>
            <input style={input} type="number" step="0.01" min="0" max="4" value={form.cgpa}
              onChange={(e) => set("cgpa", e.target.value)} />
            <label style={chk}>
              <input type="checkbox" checked={form.is_fulltime}
                onChange={(e) => set("is_fulltime", e.target.checked)} /> Full-time student
            </label>
          </section>

          <section id="additional" style={card}>
            <h2 style={h2}>Additional Information</h2>
            <label style={lbl}>Extra-curricular activities</label>
            <textarea style={{ ...input, height: 80 }} value={form.eca}
              onChange={(e) => set("eca", e.target.value)} />
            <label style={lbl}>Preferred start date</label>
            <input style={input} type="date" value={form.preferred_start_date}
              onChange={(e) => set("preferred_start_date", e.target.value)} />
            <label style={lbl}>Salary / allowance expectation (RM per month)</label>
            <div style={{ color: "#6b7280", fontSize: 12, marginTop: 2 }}>
              This field is not mandatory, but helps us understand your expectation.
            </div>
            <input style={input} type="number" min="0" value={form.salary_expectation}
              onChange={(e) => set("salary_expectation", e.target.value)} />
            <label style={lbl}>How did you hear about us?</label>
            <select style={input} value={form.heard_about_us}
              onChange={(e) => set("heard_about_us", e.target.value)}>
              <option value="">Select…</option>
              {SOURCES.map((x) => <option key={x}>{x}</option>)}
            </select>
          </section>

          <section id="consent" style={card}>
            <h2 style={h2}>Consent & Submit</h2>
            <label style={chk}>
              <input type="checkbox" checked={form.consent_talent_bank}
                onChange={(e) => set("consent_talent_bank", e.target.checked)} />{" "}
              I consent to my data being kept in the talent bank for future opportunities
            </label>
            <p style={{ color: "#6b7280", fontSize: 12 }}>
              By pressing Continue you confirm the information provided is accurate.
              Your data is processed for recruitment purposes only.
            </p>
            {error && (
              <p style={{ background: "#fee2e2", border: "1px solid #fecaca", borderRadius: 8,
                          padding: "8px 12px", color: "#dc2626", fontSize: 13 }}>
                ⚠ {error}
              </p>
            )}
            <button
              style={primary}
              disabled={busy || !form.job_id || !form.name || !form.email || !form.cgpa}
              onClick={submit}
            >
              {busy ? "Submitting…" : "Continue to Skill Assessment →"}
            </button>
          </section>
        </div>
      </div>
    </main>
  );
}

function Req() {
  return <span style={{ color: "#dc2626" }}>*</span>;
}

const jobHeader: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 12,
  background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12,
  boxShadow: "0 1px 3px rgba(16,24,40,0.06)", padding: "12px 16px", margin: "8px 0 4px",
};
const jobIcon: React.CSSProperties = {
  width: 42, height: 42, borderRadius: "50%", background: "#eef2ff",
  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18,
};
const sideNav: React.CSSProperties = {
  position: "sticky", top: 24, minWidth: 190,
  display: "flex", flexDirection: "column", gap: 18, paddingTop: 8,
};
const navItem: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 10,
  color: "#374151", textDecoration: "none", fontSize: 13.5,
};
const navDot: React.CSSProperties = {
  width: 12, height: 12, borderRadius: "50%", flexShrink: 0,
  border: "2px solid #059669", background: "#fff",
};
const card: React.CSSProperties = {
  background: "#fff", boxShadow: "0 1px 3px rgba(16,24,40,0.06)",
  border: "1px solid #e5e7eb", borderRadius: 12,
  padding: "14px 20px 18px", margin: "0 0 16px", scrollMarginTop: 20,
};
const h2: React.CSSProperties = {
  marginTop: 0, paddingBottom: 8, borderBottom: "1px solid #f1f3f5",
};
const lbl: React.CSSProperties = { display: "block", marginTop: 14, fontWeight: 600 };
const input: React.CSSProperties = {
  display: "block", width: "100%", padding: "8px 10px", marginTop: 4,
  border: "1px solid #d1d5db", borderRadius: 8, boxSizing: "border-box",
};
const chk: React.CSSProperties = { display: "block", marginTop: 10 };
const primary: React.CSSProperties = {
  padding: "10px 22px", border: "none", borderRadius: 8,
  background: "#4338ca", color: "#fff", cursor: "pointer",
};
