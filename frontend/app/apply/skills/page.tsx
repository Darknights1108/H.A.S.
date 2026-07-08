"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

type Assessment = {
  job_title: string;
  done: boolean;
  current_skills: string[];
  job_skills: string[];
  resume_skills: string[];
  resume_parse_status: "none" | "pending" | "done" | "failed";
};

function SkillsInner() {
  const params = useSearchParams();
  const token = params.get("token");
  const [data, setData] = useState<Assessment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [skills, setSkills] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [resumeExtra, setResumeExtra] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [finished, setFinished] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) {
      setError("Missing token.");
      return;
    }
    try {
      const r = await fetch(`${API}/api/skill-assessment/${token}`);
      if (!r.ok) throw new Error(r.status === 404 ? "Link not found." : `HTTP ${r.status}`);
      const d: Assessment = await r.json();
      setData(d);
      setSkills(d.current_skills ?? []);
      // skills were already AI-extracted when the resume was picked on the apply page; merge them from sessionStorage
      try {
        const cached = JSON.parse(sessionStorage.getItem("has_resume_skills") ?? "[]");
        if (Array.isArray(cached)) setResumeExtra(cached.map(String));
      } catch { /* ignore */ }
    } catch (e) {
      setError(String(e));
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  function addSkill(label: string) {
    const v = label.trim();
    if (!v) return;
    setSkills((prev) =>
      prev.some((x) => x.toLowerCase() === v.toLowerCase()) ? prev : [...prev, v]
    );
  }

  async function finish() {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${API}/api/skill-assessment/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skills }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail ?? `HTTP ${r.status}`);
      sessionStorage.removeItem("has_resume_skills");
      setFinished(d.message);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (error && !data) {
    return <main style={wrap}><p style={{ color: "#dc2626" }}>{error}</p></main>;
  }
  if (!data) return <main style={wrap}><p>Loading…</p></main>;

  if (finished || data.done) {
    return (
      <main style={{ ...wrap, textAlign: "center", marginTop: "12vh" }}>
        <h1>Thank you!</h1>
        <p>{finished ?? "Your application is complete. We will be in touch."}</p>
      </main>
    );
  }

  const have = new Set(skills.map((x) => x.toLowerCase()));
  const jobRec = data.job_skills.filter((x) => !have.has(x.toLowerCase()));
  const resumeRec = Array.from(
    new Map(
      [...data.resume_skills, ...resumeExtra].map((x) => [x.toLowerCase(), x])
    ).values()
  ).filter((x) => !have.has(x.toLowerCase()));

  return (
    <main style={wrap}>
      <h1>Skill Assessment</h1>
      <p style={{ color: "#6b7280" }}>
        One last step for <b>{data.job_title}</b> — tell us your skills. Add them
        manually, or pick from the recommendations below.
      </p>

      <section style={card}>
        <h2 style={h2}>Your skills ({skills.length})</h2>
        {skills.length === 0 && (
          <p style={{ color: "#6b7280", fontSize: 13 }}>No skills added yet.</p>
        )}
        <div style={chipRow}>
          {skills.map((x) => (
            <span key={x} style={chipSelected}>
              {x}
              <button style={chipBtn} onClick={() => setSkills(skills.filter((y) => y !== x))}>
                ×
              </button>
            </span>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <input
            style={{ ...inputStyle, flex: 1 }}
            placeholder="Type a skill, e.g. Excel, Public speaking, Python…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                addSkill(input);
                setInput("");
              }
            }}
          />
          <button style={{ ...primary, padding: "8px 16px" }}
            onClick={() => { addSkill(input); setInput(""); }}>
            Add
          </button>
        </div>
      </section>

      {jobRec.length > 0 && (
        <section style={card}>
          <h2 style={h2}>From the job requirements</h2>
          <p style={{ color: "#6b7280", fontSize: 13 }}>
            Skills this role is looking for — click to add the ones you have.
          </p>
          <div style={chipRow}>
            {jobRec.map((x) => (
              <button key={x} style={chipSuggested} onClick={() => addSkill(x)}>
                {x} +
              </button>
            ))}
          </div>
        </section>
      )}

      {(resumeRec.length > 0 || data.resume_parse_status === "pending") && (
        <section style={card}>
          <h2 style={h2}>From your resume</h2>
          {resumeRec.length > 0 ? (
            <div style={chipRow}>
              {resumeRec.map((x) => (
                <button key={x} style={chipSuggested} onClick={() => addSkill(x)}>
                  {x} +
                </button>
              ))}
            </div>
          ) : (
            <p style={{ color: "#6b7280", fontSize: 13 }}>
              Your resume is still being analyzed — you can continue without waiting.
            </p>
          )}
        </section>
      )}

      {error && <p style={{ color: "#dc2626" }}>{error}</p>}
      <p>
        <button style={primary} disabled={busy} onClick={finish}>
          {busy ? "Submitting…" : "Finish application"}
        </button>
      </p>
    </main>
  );
}

export default function SkillAssessmentPage() {
  return (
    <Suspense fallback={<main style={wrap}><p>Loading…</p></main>}>
      <SkillsInner />
    </Suspense>
  );
}

const wrap: React.CSSProperties = { maxWidth: 720, margin: "0 auto" };
const card: React.CSSProperties = {
  background: "#fff", boxShadow: "0 1px 3px rgba(16,24,40,0.06)",
  border: "1px solid #e5e7eb", borderRadius: 12,
  padding: "14px 20px 18px", margin: "0 0 16px",
};
const h2: React.CSSProperties = {
  marginTop: 0, paddingBottom: 8, borderBottom: "1px solid #f1f3f5",
};
const inputStyle: React.CSSProperties = {
  padding: "8px 10px", border: "1px solid #d1d5db", borderRadius: 8, boxSizing: "border-box",
};
const primary: React.CSSProperties = {
  padding: "10px 22px", border: "none", borderRadius: 8,
  background: "#4338ca", color: "#fff", cursor: "pointer",
};
const chipRow: React.CSSProperties = { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 };
const chipSelected: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 4,
  background: "#eef2ff", color: "#4338ca", fontWeight: 600,
  borderRadius: 999, padding: "4px 6px 4px 12px", fontSize: 13,
};
const chipBtn: React.CSSProperties = {
  border: "none", background: "transparent", color: "#4338ca",
  fontSize: 15, lineHeight: 1, padding: "0 6px", cursor: "pointer",
};
const chipSuggested: React.CSSProperties = {
  background: "#fff", color: "#374151", border: "1px dashed #9ca3af",
  borderRadius: 999, padding: "4px 12px", fontSize: 13, cursor: "pointer",
};
