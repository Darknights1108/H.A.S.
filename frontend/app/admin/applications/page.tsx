"use client";

import { useCallback, useEffect, useState } from "react";

import AdminBar from "@/components/AdminBar";
import { useSession } from "@/lib/session";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

type Row = {
  id: string;
  candidate: { name: string; email: string };
  job_title: string;
  cgpa: number | null;
  degree_field: string | null;
  prog_langs: string[];
  status: string;
  rejected_reason: string | null;
  band: string | null;
  total_score: number | null;
  reasoning: string | null;
  booking_url: string;
  submitted_at: string;
  interview: { date: string; start: string; end: string; meeting_link: string | null } | null;
};

export default function AdminApplicationsPage() {
  const { session, loading: authLoading } = useSession(true);
  const [rows, setRows] = useState<Row[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  // 二次确认:待确认的面试结果 {申请id, 结果} —— 防误点
  const [pending, setPending] = useState<{ id: string; result: "passed" | "failed" } | null>(null);

  const load = useCallback(async () => {
    const r = await fetch(`${API}/api/applications`);
    if (r.ok) setRows(await r.json());
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function act(id: string, action: "approve" | "reject") {
    setNotice(null);
    const r = await fetch(`${API}/api/applications/${id}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: action === "reject" ? JSON.stringify({ reason: "manual" }) : undefined,
    });
    const data = await r.json();
    if (!r.ok) setNotice(data.detail ?? `HTTP ${r.status}`);
    else if (action === "approve") setNotice(`Invite drafted — booking link: ${data.booking_url}`);
    await load();
  }

  async function outcome(id: string, result: "passed" | "failed") {
    setNotice(null);
    setPending(null);
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
          ? "✅ 已 Accept — offer 信草稿已生成,请到 Emails 页审核发送"
          : "✅ 已 Reject — 婉拒信草稿已生成,请到 Emails 页审核发送"
      );
    await load();
  }

  if (authLoading || !session) return <main><p>Loading…</p></main>;

  return (
    <main style={{ maxWidth: 1000 }}>
      <AdminBar session={session} />
      <h1>Applications review</h1>
      {notice && <p style={{ color: "#06c", wordBreak: "break-all" }}>{notice}</p>}
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th style={th}>Candidate</th><th style={th}>Job</th><th style={th}>CGPA</th>
            <th style={th}>Band</th><th style={th}>Score</th><th style={th}>Status</th>
            <th style={th}>Interview</th><th style={th}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <>
              <tr key={r.id}>
                <td style={td}>
                  {r.candidate.name}
                  <div style={{ color: "#888", fontSize: 12 }}>{r.candidate.email}</div>
                </td>
                <td style={td}>{r.job_title}</td>
                <td style={td}>{r.cgpa ?? "—"}</td>
                <td style={td}>
                  {r.band && <span style={{ ...badge, ...bandColor[r.band] }}>{r.band}</span>}
                </td>
                <td style={td}>{r.total_score ?? "—"}</td>
                <td style={td}>
                  {r.status}
                  {r.rejected_reason && (
                    <div style={{ color: "#888", fontSize: 12 }}>{r.rejected_reason}</div>
                  )}
                </td>
                <td style={td}>
                  {r.interview ? (
                    <>
                      {r.interview.date}
                      <div style={{ color: "#888", fontSize: 12 }}>
                        {r.interview.start}–{r.interview.end}
                      </div>
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td style={td}>
                  <button style={btnSm} onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                    Why?
                  </button>{" "}
                  {r.status === "shortlisted" && (
                    <>
                      <button style={{ ...btnSm, background: "#0a6" }} onClick={() => act(r.id, "approve")}>
                        Approve
                      </button>{" "}
                      <button style={{ ...btnSm, background: "#b33" }} onClick={() => act(r.id, "reject")}>
                        Reject
                      </button>
                    </>
                  )}
                  {r.status === "scheduled" && r.interview && pending?.id !== r.id && (
                    <>
                      <button
                        style={{ ...btnSm, background: "#0a6" }}
                        onClick={() => setPending({ id: r.id, result: "passed" })}
                      >
                        Accept
                      </button>{" "}
                      <button
                        style={{ ...btnSm, background: "#b33" }}
                        onClick={() => setPending({ id: r.id, result: "failed" })}
                      >
                        Reject
                      </button>
                    </>
                  )}
                  {pending?.id === r.id && (
                    <span style={confirmBox}>
                      确认将 <b>{r.candidate.name}</b> 标记为{" "}
                      <b style={{ color: pending.result === "passed" ? "#0a6" : "#b33" }}>
                        {pending.result === "passed" ? "Accept(发 offer)" : "Reject(发婉拒信)"}
                      </b>
                      ?此操作不可撤销。{" "}
                      <button
                        style={{ ...btnSm, background: pending.result === "passed" ? "#0a6" : "#b33" }}
                        onClick={() => outcome(r.id, pending.result)}
                      >
                        确认
                      </button>{" "}
                      <button style={{ ...btnSm, background: "#888" }} onClick={() => setPending(null)}>
                        取消
                      </button>
                    </span>
                  )}
                </td>
              </tr>
              {expanded === r.id && (
                <tr key={r.id + "-detail"}>
                  <td style={{ ...td, background: "#fafafa" }} colSpan={8}>
                    <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 13 }}>
                      {r.reasoning ?? "no score"}
                    </pre>
                    <p style={{ fontSize: 12, color: "#888", marginBottom: 0 }}>
                      Booking link: {r.booking_url}
                    </p>
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

const th: React.CSSProperties = { textAlign: "left", borderBottom: "2px solid #ddd", padding: 8 };
const td: React.CSSProperties = { borderBottom: "1px solid #eee", padding: 8, verticalAlign: "top" };
const badge: React.CSSProperties = { padding: "2px 10px", borderRadius: 10, fontSize: 12 };
const bandColor: Record<string, React.CSSProperties> = {
  high: { background: "#d8f5e8", color: "#0a6" },
  medium: { background: "#fef3c7", color: "#92600a" },
  low: { background: "#fee2e2", color: "#b33" },
};
const btnSm: React.CSSProperties = {
  padding: "4px 10px", border: "none", borderRadius: 4,
  background: "#334", color: "#fff", cursor: "pointer", fontSize: 12,
};
const confirmBox: React.CSSProperties = {
  display: "inline-block", background: "#fff8e1", border: "1px solid #f0d264",
  borderRadius: 6, padding: "6px 10px", fontSize: 12,
};
