"use client";

import { useCallback, useEffect, useState } from "react";

import AdminBar from "@/components/AdminBar";
import { useSession } from "@/lib/session";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

type EmailRow = {
  id: string; type: string; to: string; candidate_name: string;
  subject: string; body: string; status: string;
  created_at: string; sent_at: string | null;
};

export default function AdminEmailsPage() {
  const { session, loading: authLoading } = useSession(true);
  const [emails, setEmails] = useState<EmailRow[]>([]);
  const [smtpConfigured, setSmtpConfigured] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch(`${API}/api/emails`);
    if (r.ok) {
      const data = await r.json();
      setEmails(data.emails);
      setSmtpConfigured(data.smtp_configured);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function send(id: string) {
    setBusy(id);
    setNotice(null);
    try {
      const r = await fetch(`${API}/api/emails/${id}/send`, { method: "POST" });
      const data = await r.json();
      if (!r.ok) setNotice(data.detail ?? `HTTP ${r.status}`);
      else setNotice("Sent ✅");
      await load();
    } finally {
      setBusy(null);
    }
  }

  if (authLoading || !session) return <main><p>Loading…</p></main>;

  return (
    <main style={{ maxWidth: 900 }}>
      <AdminBar session={session} />
      <h1>Email outbox</h1>
      {!smtpConfigured && (
        <p style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "8px 12px" }}>
          ⚠ SMTP not configured — set SMTP_HOST / SMTP_USER / SMTP_PASSWORD in the root .env and restart the backend to enable real sending.
        </p>
      )}
      {notice && <p style={{ color: notice.includes("✅") ? "#059669" : "#dc2626" }}>{notice}</p>}

      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th style={th}>Type</th><th style={th}>To</th><th style={th}>Subject</th>
            <th style={th}>Status</th><th style={th}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {emails.map((e) => (
            <>
              <tr key={e.id}>
                <td style={td}><span style={{ ...badge, ...typeColor[e.type] }}>{e.type}</span></td>
                <td style={td}>
                  {e.candidate_name}
                  <div style={{ color: "#6b7280", fontSize: 12 }}>{e.to}</div>
                </td>
                <td style={td}>{e.subject}</td>
                <td style={td}>
                  {e.status === "sent" ? (
                    <span style={{ color: "#059669" }}>sent ✓</span>
                  ) : (
                    <span style={{ color: "#b45309" }}>draft</span>
                  )}
                  {e.sent_at && (
                    <div style={{ color: "#6b7280", fontSize: 11 }}>{e.sent_at.slice(0, 16).replace("T", " ")}</div>
                  )}
                </td>
                <td style={td}>
                  <button style={btnSm} onClick={() => setExpanded(expanded === e.id ? null : e.id)}>
                    Preview
                  </button>{" "}
                  {e.status === "draft" && (
                    <button
                      style={{ ...btnSm, background: "#059669" }}
                      disabled={busy === e.id}
                      onClick={() => send(e.id)}
                    >
                      {busy === e.id ? "Sending…" : "Send"}
                    </button>
                  )}
                </td>
              </tr>
              {expanded === e.id && (
                <tr key={e.id + "-body"}>
                  <td style={{ ...td, background: "#f9fafb" }} colSpan={5}>
                    <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 13 }}>{e.body}</pre>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </main>
  );
}

const th: React.CSSProperties = { textAlign: "left", borderBottom: "2px solid #e5e7eb", padding: 8 };
const td: React.CSSProperties = { borderBottom: "1px solid #f1f3f5", padding: 8, verticalAlign: "top" };
const badge: React.CSSProperties = { padding: "2px 10px", borderRadius: 999, fontSize: 12 };
const typeColor: Record<string, React.CSSProperties> = {
  invite: { background: "#e0e7ff", color: "#3730a3" },
  confirmation: { background: "#d1fae5", color: "#059669" },
  reschedule: { background: "#fef3c7", color: "#92600a" },
  offer: { background: "#d1fae5", color: "#059669" },
  reject: { background: "#fee2e2", color: "#dc2626" },
};
const btnSm: React.CSSProperties = {
  padding: "4px 10px", border: "none", borderRadius: 8,
  background: "#4338ca", color: "#fff", cursor: "pointer", fontSize: 12,
};
