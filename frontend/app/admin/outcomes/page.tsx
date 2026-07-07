"use client";

import { useCallback, useEffect, useState } from "react";
import AdminBar from "@/components/AdminBar";
import { API, useSession } from "@/lib/session";

type Row = {
  id: string;
  candidate: { name: string; email: string };
  job_title: string;
  band: string | null;
  total_score: number | null;
  status: string;
  rejected_reason: string | null;
  interview: {
    date: string; start: string; end: string;
    meeting_link: string | null; panel: string[];
  } | null;
  resume: { uploaded: boolean; status: string; parsed: { jd_match?: { match_score?: number; verdict?: string } } | null };
};

export default function OutcomesPage() {
  const { session, loading } = useSession(true);
  const [rows, setRows] = useState<Row[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState<{ id: string; result: "passed" | "failed" } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch(`${API}/api/applications`);
    if (r.ok) setRows(await r.json());
  }, []);

  useEffect(() => {
    if (session) load();
  }, [session, load]);

  async function decide(id: string, result: "passed" | "failed") {
    setBusy(true);
    setNotice(null);
    setPending(null);
    try {
      const r = await fetch(`${API}/api/applications/${id}/outcome`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result }),
      });
      const data = await r.json();
      if (!r.ok) setNotice(data.detail ?? `HTTP ${r.status}`);
      else
        setNotice(
          result === "passed"
            ? "✅ Accepted — offer letter drafted, review & send it on the Emails page"
            : "✅ Rejected — rejection letter drafted, review & send it on the Emails page"
        );
      await load();
    } finally {
      setBusy(false);
    }
  }

  if (loading || !session) return <main><p>Loading…</p></main>;

  const now = new Date();
  const scheduled = rows.filter((r) => r.status === "scheduled" && r.interview);
  const isDue = (r: Row) =>
    new Date(`${r.interview!.date}T${r.interview!.end}:00`) <= now;
  const due = scheduled.filter(isDue);
  const upcoming = scheduled.filter((r) => !isDue(r));
  const decided = rows
    .filter((r) => r.status === "passed" || r.rejected_reason === "interview_failed")
    .slice(0, 10);

  const matchScore = (r: Row) => r.resume.parsed?.jd_match?.match_score;

  return (
    <main style={{ maxWidth: 900 }}>
      <AdminBar session={session} />
      <h1>Interview outcomes</h1>
      <p style={{ color: "#6b7280" }}>
        Decide on candidates after their interview. Accept drafts an offer
        letter; Reject drafts a rejection letter — both go to the Emails page
        for review before sending.
      </p>
      {notice && <p style={{ color: "#2563eb" }}>{notice}</p>}

      <section style={card}>
        <h2 style={h2}>
          Awaiting decision{" "}
          <span style={{ ...badge, background: due.length ? "#fee2e2" : "#f1f3f5",
                         color: due.length ? "#dc2626" : "#6b7280" }}>
            {due.length}
          </span>
        </h2>
        {due.length === 0 && (
          <p style={{ color: "#6b7280", fontSize: 13 }}>
            No interviews waiting for a decision.
          </p>
        )}
        {due.map((r) => (
          <div key={r.id} style={itemRow}>
            <div style={{ flex: 1, minWidth: 220 }}>
              <b>{r.candidate.name}</b>
              <div style={sub}>{r.candidate.email}</div>
              <div style={sub}>{r.job_title}</div>
            </div>
            <div style={{ flex: 1, minWidth: 200 }}>
              <div style={{ fontSize: 13 }}>
                🗓 {r.interview!.date} {r.interview!.start}–{r.interview!.end}
              </div>
              <div style={sub}>Panel: {r.interview!.panel.join(", ") || "—"}</div>
              <div style={sub}>
                {r.band && <>screening: <b>{r.band}</b> ({r.total_score ?? "—"})</>}
                {matchScore(r) != null && <> · JD match: <b>{Math.round(matchScore(r)!)}/100</b></>}
              </div>
            </div>
            <div style={{ whiteSpace: "nowrap" }}>
              <button style={{ ...btn, background: "#059669" }} disabled={busy}
                onClick={() => setPending({ id: r.id, result: "passed" })}>
                Accept
              </button>{" "}
              <button style={{ ...btn, background: "#dc2626" }} disabled={busy}
                onClick={() => setPending({ id: r.id, result: "failed" })}>
                Reject
              </button>
            </div>
            {pending?.id === r.id && (
              <div style={confirmBox}>
                ⚠ Confirm marking <b>{r.candidate.name}</b> as{" "}
                <b style={{ color: pending.result === "passed" ? "#059669" : "#dc2626" }}>
                  {pending.result === "passed"
                    ? "ACCEPTED (offer letter will be drafted)"
                    : "REJECTED (rejection letter will be drafted)"}
                </b>
                ? This cannot be undone.{" "}
                <button
                  style={{ ...btn, background: pending.result === "passed" ? "#059669" : "#dc2626" }}
                  onClick={() => decide(r.id, pending.result)}
                >
                  Confirm
                </button>{" "}
                <button style={{ ...btn, background: "#6b7280" }} onClick={() => setPending(null)}>
                  Cancel
                </button>
              </div>
            )}
          </div>
        ))}
      </section>

      <section style={card}>
        <h2 style={h2}>Upcoming interviews <span style={{ ...badge, background: "#e0e7ff", color: "#4338ca" }}>{upcoming.length}</span></h2>
        {upcoming.length === 0 && (
          <p style={{ color: "#6b7280", fontSize: 13 }}>None scheduled.</p>
        )}
        {upcoming.map((r) => (
          <div key={r.id} style={itemRow}>
            <div style={{ flex: 1 }}>
              <b>{r.candidate.name}</b> <span style={sub}>· {r.job_title}</span>
            </div>
            <div style={{ fontSize: 13 }}>
              🗓 {r.interview!.date} {r.interview!.start}–{r.interview!.end}
              <span style={sub}> · {r.interview!.panel.join(", ") || "—"}</span>
            </div>
          </div>
        ))}
      </section>

      <section style={card}>
        <h2 style={h2}>Recent decisions</h2>
        {decided.length === 0 && (
          <p style={{ color: "#6b7280", fontSize: 13 }}>None yet.</p>
        )}
        {decided.map((r) => (
          <div key={r.id} style={itemRow}>
            <div style={{ flex: 1 }}>
              <b>{r.candidate.name}</b> <span style={sub}>· {r.job_title}</span>
            </div>
            <span style={{
              ...badge,
              background: r.status === "passed" ? "#d1fae5" : "#fee2e2",
              color: r.status === "passed" ? "#059669" : "#dc2626",
            }}>
              {r.status === "passed" ? "accepted ✓" : "rejected"}
            </span>
          </div>
        ))}
      </section>
    </main>
  );
}

const card: React.CSSProperties = {
  background: "#fff", boxShadow: "0 1px 3px rgba(16,24,40,0.06)",
  border: "1px solid #e5e7eb", borderRadius: 12,
  padding: "14px 20px", margin: "0 0 16px",
};
const h2: React.CSSProperties = { marginTop: 0, paddingBottom: 8, borderBottom: "1px solid #f1f3f5" };
const itemRow: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
  padding: "10px 0", borderBottom: "1px solid #f1f3f5",
};
const sub: React.CSSProperties = { color: "#6b7280", fontSize: 12 };
const badge: React.CSSProperties = { padding: "2px 10px", borderRadius: 999, fontSize: 12 };
const btn: React.CSSProperties = {
  padding: "6px 14px", border: "none", borderRadius: 8,
  background: "#4338ca", color: "#fff", cursor: "pointer", fontSize: 13,
};
const confirmBox: React.CSSProperties = {
  flexBasis: "100%", background: "#fffbeb", border: "1px solid #fde68a",
  borderRadius: 8, padding: "8px 12px", fontSize: 13,
};
