"use client";

import { useCallback, useEffect, useState } from "react";
import AdminBar from "@/components/AdminBar";
import { API, useSession } from "@/lib/session";

type Setting = {
  key: string;
  value: number | string;
  description: string | null;
  type: "int" | "str";
  updated_at: string;
};

const LABELS: Record<string, string> = {
  shortlist_review_days: "Shortlist 审查期限(天)",
  slot_duration_minutes: "面试时段长度(分钟)",
  panel_max_interviewers: "单时段面试官上限(panel)",
  reschedule_max: "改期次数上限(0 = 不限)",
  company_name: "公司名(信件署名)",
};

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
      else setNotice(`✅ ${LABELS[s.key] ?? s.key} 已更新,立即生效`);
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
      <p style={{ color: "#666" }}>
        改动即时生效(定时任务、panel 上限、改期限制、信件署名都动态读取这些值)。
      </p>
      {notice && (
        <p style={{ color: notice.startsWith("✅") ? "#0a6" : "#b00" }}>{notice}</p>
      )}

      {rows.map((s) => {
        const dirty = drafts[s.key] !== String(s.value);
        return (
          <section key={s.key} style={card}>
            <label style={{ fontWeight: 600 }}>{LABELS[s.key] ?? s.key}</label>
            <div style={{ color: "#888", fontSize: 12, margin: "2px 0 8px" }}>
              {s.description}
              {" · "}上次修改 {s.updated_at.slice(0, 16).replace("T", " ")}
            </div>
            <input
              style={input}
              type={s.type === "int" ? "number" : "text"}
              value={drafts[s.key] ?? ""}
              onChange={(e) => setDrafts({ ...drafts, [s.key]: e.target.value })}
            />{" "}
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
  border: "1px solid #ddd", borderRadius: 8, padding: "12px 16px", margin: "12px 0",
};
const input: React.CSSProperties = {
  padding: "8px 10px", border: "1px solid #ccc", borderRadius: 6, width: 260,
};
const btn: React.CSSProperties = {
  padding: "8px 18px", border: "none", borderRadius: 6,
  background: "#334", color: "#fff", cursor: "pointer",
};
