"use client";

import { useCallback, useEffect, useState } from "react";
import AdminBar from "@/components/AdminBar";
import { API, useSession } from "@/lib/session";

type Setting = {
  key: string;
  value: number | string;
  description: string | null;
  type: "int" | "str";
  multiline: boolean;
  updated_at: string;
};

const LABELS: Record<string, string> = {
  shortlist_review_days: "Shortlist review window (days)",
  slot_duration_minutes: "Interview slot length (minutes)",
  panel_max_interviewers: "Max interviewers per slot (panel)",
  reschedule_max: "Max reschedules (0 = unlimited)",
  candidate_response_days: "Candidate response window (days after invite)",
  work_start_hour: "Working hours start (hour, for slot generation)",
  work_end_hour: "Working hours end (hour, exclusive)",
  company_name: "Company name (letter signature)",
  invite_email_subject: "Invite email subject",
  invite_email_template: "Invite email body template",
};

const PLACEHOLDER_HINT =
  "Placeholders: {candidate_name} · {job_title} · {booking_url} · {company_name}";
const TEMPLATE_KEYS = new Set(["invite_email_subject", "invite_email_template"]);

export default function AdminSettingsPage() {
  const { session, loading } = useSession(true);
  const [rows, setRows] = useState<Setting[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch(`${API}/api/settings`);
    if (r.ok) {
      const data: Setting[] = await r.json();
      setRows(data);
      setDrafts(Object.fromEntries(data.map((s) => [s.key, String(s.value)])));
    }
  }, []);

  useEffect(() => {
    if (session) load();
  }, [session, load]);

  async function save(s: Setting) {
    setBusy(s.key);
    setNotice(null);
    try {
      const raw = drafts[s.key];
      const r = await fetch(`${API}/api/settings/${s.key}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value: s.type === "int" ? Number(raw) : raw }),
      });
      const data = await r.json();
      if (!r.ok) setNotice(`${s.key}: ${data.detail ?? `HTTP ${r.status}`}`);
      else setNotice(`✅ ${LABELS[s.key] ?? s.key} updated — effective immediately`);
      await load();
    } finally {
      setBusy(null);
    }
  }

  if (loading || !session) return <main><p>Loading…</p></main>;

  return (
    <main style={{ maxWidth: 720 }}>
      <AdminBar session={session} />
      <h1>Settings</h1>
      <p style={{ color: "#6b7280" }}>
        Changes take effect immediately — timers, panel caps, reschedule limits
        and letter templates all read these values live.
      </p>
      {notice && (
        <p style={{ color: notice.startsWith("✅") ? "#059669" : "#dc2626" }}>{notice}</p>
      )}

      {rows.map((s) => {
        const dirty = drafts[s.key] !== String(s.value);
        return (
          <section key={s.key} style={card}>
            <label style={{ fontWeight: 600 }}>{LABELS[s.key] ?? s.key}</label>
            <div style={{ color: "#6b7280", fontSize: 12, margin: "2px 0 8px" }}>
              {s.description}
              {" · "}last modified {s.updated_at.slice(0, 16).replace("T", " ")}
            </div>
            {s.multiline ? (
              <textarea
                style={{ ...input, width: "100%", height: 200, fontFamily: "inherit", boxSizing: "border-box" }}
                value={drafts[s.key] ?? ""}
                onChange={(e) => setDrafts({ ...drafts, [s.key]: e.target.value })}
              />
            ) : (
              <input
                style={input}
                type={s.type === "int" ? "number" : "text"}
                value={drafts[s.key] ?? ""}
                onChange={(e) => setDrafts({ ...drafts, [s.key]: e.target.value })}
              />
            )}
            {TEMPLATE_KEYS.has(s.key) && (
              <div style={{ color: "#6b7280", fontSize: 12, margin: "6px 0" }}>{PLACEHOLDER_HINT}</div>
            )}{" "}
            <button
              style={{ ...btn, opacity: dirty ? 1 : 0.4 }}
              disabled={!dirty || busy === s.key}
              onClick={() => save(s)}
            >
              {busy === s.key ? "Saving…" : "Save"}
            </button>
          </section>
        );
      })}
    </main>
  );
}

const card: React.CSSProperties = {
  background: "#fff", boxShadow: "0 1px 3px rgba(16,24,40,0.06)", border: "1px solid #e5e7eb", borderRadius: 12, padding: "12px 16px", margin: "12px 0",
};
const input: React.CSSProperties = {
  padding: "8px 10px", border: "1px solid #d1d5db", borderRadius: 8, width: 260,
};
const btn: React.CSSProperties = {
  padding: "8px 18px", border: "none", borderRadius: 8,
  background: "#4338ca", color: "#fff", cursor: "pointer",
};
