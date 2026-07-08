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
  invite_status: "none" | "draft" | "sent";
  resume: {
    uploaded: boolean;
    status: "none" | "pending" | "done" | "failed";
    parsed: ResumeParsed | null;
  };
};

type ResumeParsed = {
  summary?: string;
  education?: { institution?: string; degree?: string; field?: string; cgpa?: number | null }[];
  experience_projects?: { title?: string; organization?: string; description?: string }[];
  programming_languages?: string[];
  other_skills?: string[];
  ai_evidence?: string[];
  extracurricular?: string[];
  consistency_notes?: string[];
  jd_match?: {
    must_have?: MatchItem[];
    nice_to_have?: MatchItem[];
    match_score?: number;
    verdict?: string;
  };
  model?: string;
  error?: string;
};

type MatchItem = { criterion: string; met: "yes" | "partial" | "no" | "unknown"; evidence: string };

export default function AdminApplicationsPage() {
  const { session, loading: authLoading } = useSession(true);
  const [rows, setRows] = useState<Row[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  // second confirmation: pending outcome {application id, result} — prevents misclicks
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
    else if (action === "approve")
      setNotice(
        data.already
          ? `Invite was already ${data.already === "sent" ? "sent" : "drafted"} for this candidate`
          : "✅ Invite drafted — review & send it on the Emails page"
      );
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
          ? data.offer_sent
            ? "✅ Accepted — offer letter sent to the candidate"
            : "✅ Accepted — offer drafted but sending failed; send it manually on the Emails page"
          : "✅ Rejected — rejection letter drafted, review & send it on the Emails page"
      );
    await load();
  }

  if (authLoading || !session) return <main><p>Loading…</p></main>;

  return (
    <main style={{ maxWidth: 1000 }}>
      <AdminBar session={session} />
      <h1>Applications review</h1>
      {notice && <p style={{ color: "#2563eb", wordBreak: "break-all" }}>{notice}</p>}
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th style={th}>Candidate</th><th style={th}>Job</th>
            <th style={th}>Screening</th><th style={th}>Status</th>
            <th style={th}>Resume</th><th style={{ ...th, width: 210 }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <>
              <tr key={r.id}>
                <td style={td}>
                  {r.candidate.name}
                  <div style={sub}>{r.candidate.email}</div>
                </td>
                <td style={td}>{r.job_title}</td>
                <td style={td}>
                  {r.band && <span style={{ ...badge, ...bandColor[r.band] }}>{r.band}</span>}
                  <div style={sub}>
                    score {r.total_score ?? "—"} · CGPA {r.cgpa ?? "—"}
                  </div>
                </td>
                <td style={td}>
                  {r.status}
                  {r.rejected_reason && <div style={sub}>{r.rejected_reason}</div>}
                  {r.invite_status === "draft" && (
                    <div style={{ ...sub, color: "#b45309" }}>✉ invite drafted — send it in Emails</div>
                  )}
                  {r.invite_status === "sent" && (
                    <div style={{ ...sub, color: "#059669" }}>✉ invite sent</div>
                  )}
                  {r.interview && (
                    <div style={sub}>
                      🗓 {r.interview.date} {r.interview.start}–{r.interview.end}
                    </div>
                  )}
                </td>
                <td style={td}>
                  {!r.resume.uploaded ? (
                    "—"
                  ) : (
                    <span style={{ ...badge, ...resumeColor[r.resume.status], whiteSpace: "nowrap" }}>
                      {r.resume.status === "done" ? "parsed ✓" : r.resume.status}
                    </span>
                  )}
                </td>
                <td style={{ ...td, whiteSpace: "nowrap" }}>
                  <button style={btnSm} onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                    Why?
                  </button>{" "}
                  {r.status === "shortlisted" && (
                    <>
                      {r.invite_status === "none" ? (
                        <button style={{ ...btnSm, background: "#059669" }} onClick={() => act(r.id, "approve")}>
                          Approve
                        </button>
                      ) : (
                        <span style={{ ...btnSm, background: "#f3f4f6", color: "#059669", cursor: "default" }}>
                          Invited ✓
                        </span>
                      )}{" "}
                      <button style={{ ...btnSm, background: "#dc2626" }} onClick={() => act(r.id, "reject")}>
                        Reject
                      </button>
                    </>
                  )}
                  {r.status === "scheduled" && r.interview && (
                    <>
                      <button
                        style={{ ...btnSm, background: "#059669" }}
                        onClick={() => setPending({ id: r.id, result: "passed" })}
                      >
                        Accept
                      </button>{" "}
                      <button
                        style={{ ...btnSm, background: "#dc2626" }}
                        onClick={() => setPending({ id: r.id, result: "failed" })}
                      >
                        Reject
                      </button>
                    </>
                  )}
                </td>
              </tr>
              {pending?.id === r.id && (
                <tr key={r.id + "-confirm"}>
                  <td style={{ ...td, ...confirmRow }} colSpan={6}>
                    ⚠ Confirm marking <b>{r.candidate.name}</b> as{" "}
                    <b style={{ color: pending.result === "passed" ? "#059669" : "#dc2626" }}>
                      {pending.result === "passed"
                        ? "ACCEPTED (offer letter will be SENT immediately)"
                        : "REJECTED (rejection letter will be drafted)"}
                    </b>
                    ? This cannot be undone.{" "}
                    <button
                      style={{ ...btnSm, background: pending.result === "passed" ? "#059669" : "#dc2626" }}
                      onClick={() => outcome(r.id, pending.result)}
                    >
                      Confirm
                    </button>{" "}
                    <button style={{ ...btnSm, background: "#6b7280" }} onClick={() => setPending(null)}>
                      Cancel
                    </button>
                  </td>
                </tr>
              )}
              {expanded === r.id && (
                <tr key={r.id + "-detail"}>
                  <td style={{ ...td, background: "#f9fafb" }} colSpan={6}>
                    <b style={{ fontSize: 13 }}>Score reasoning</b>
                    <pre style={{ whiteSpace: "pre-wrap", margin: "4px 0 12px", fontSize: 13 }}>
                      {r.reasoning ?? "no score"}
                    </pre>
                    {r.resume.uploaded && r.resume.parsed && r.resume.status === "done" && (
                      <div style={{ borderTop: "1px solid #f1f3f5", paddingTop: 8 }}>
                        <b style={{ fontSize: 13 }}>
                          Resume analysis{" "}
                          <a href={`${API}/api/applications/${r.id}/resume`} style={{ fontSize: 12 }}>
                            [download original]
                          </a>
                        </b>
                        <p style={{ fontSize: 13, margin: "6px 0" }}>{r.resume.parsed.summary}</p>
                        {(r.resume.parsed.programming_languages?.length ?? 0) > 0 && (
                          <p style={{ fontSize: 13, margin: "4px 0" }}>
                            <b>Languages:</b> {r.resume.parsed.programming_languages!.join(", ")}
                          </p>
                        )}
                        {(r.resume.parsed.ai_evidence?.length ?? 0) > 0 && (
                          <p style={{ fontSize: 13, margin: "4px 0" }}>
                            <b>AI evidence:</b> {r.resume.parsed.ai_evidence!.join(" · ")}
                          </p>
                        )}
                        {(r.resume.parsed.consistency_notes?.length ?? 0) > 0 && (
                          <div style={{ background: "#fffbeb", border: "1px solid #fde68a",
                                        borderRadius: 8, padding: "6px 10px", marginTop: 6 }}>
                            <b style={{ fontSize: 13 }}>Form cross-check</b>
                            <ul style={{ margin: "4px 0", fontSize: 13 }}>
                              {r.resume.parsed.consistency_notes!.map((n, i) => <li key={i}>{n}</li>)}
                            </ul>
                          </div>
                        )}
                        {r.resume.parsed.jd_match &&
                          ((r.resume.parsed.jd_match.must_have?.length ?? 0) > 0 ||
                            (r.resume.parsed.jd_match.nice_to_have?.length ?? 0) > 0) && (
                          <div style={{ background: "#eef2ff", border: "1px solid #c7d2fe",
                                        borderRadius: 12, padding: "8px 12px", marginTop: 8 }}>
                            <b style={{ fontSize: 13 }}>
                              JD match
                              {r.resume.parsed.jd_match.match_score != null &&
                                ` — ${Math.round(r.resume.parsed.jd_match.match_score)}/100`}
                            </b>
                            {r.resume.parsed.jd_match.verdict && (
                              <p style={{ fontSize: 13, margin: "4px 0 8px" }}>
                                {r.resume.parsed.jd_match.verdict}
                              </p>
                            )}
                            <MatchList label="Must have" items={r.resume.parsed.jd_match.must_have} />
                            <MatchList label="Nice to have" items={r.resume.parsed.jd_match.nice_to_have} />
                          </div>
                        )}
                      </div>
                    )}
                    {r.resume.status === "failed" && (
                      <p style={{ fontSize: 13, color: "#dc2626" }}>
                        Resume parse failed: {r.resume.parsed?.error ?? "unknown"}{" "}
                        <a href={`${API}/api/applications/${r.id}/resume`}>[download original]</a>
                      </p>
                    )}
                    <p style={{ fontSize: 12, color: "#6b7280", marginBottom: 0 }}>
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

function MatchList({ label, items }: { label: string; items?: MatchItem[] }) {
  if (!items || items.length === 0) return null;
  const icon: Record<MatchItem["met"], string> = {
    yes: "✓", partial: "◐", no: "✗", unknown: "?",
  };
  const color: Record<MatchItem["met"], string> = {
    yes: "#059669", partial: "#b45309", no: "#dc2626", unknown: "#6b7280",
  };
  return (
    <div style={{ marginTop: 4 }}>
      <div style={{ fontSize: 12.5, fontWeight: 600 }}>{label}</div>
      <ul style={{ margin: "4px 0", paddingLeft: 18 }}>
        {items.map((m, i) => (
          <li key={i} style={{ fontSize: 13, margin: "2px 0" }}>
            <b style={{ color: color[m.met] }}>{icon[m.met]}</b> {m.criterion}
            <span style={{ color: "#6b7280" }}> — {m.evidence}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const th: React.CSSProperties = { textAlign: "left", borderBottom: "2px solid #e5e7eb", padding: 8 };
const td: React.CSSProperties = { borderBottom: "1px solid #f1f3f5", padding: 8, verticalAlign: "top" };
const badge: React.CSSProperties = { padding: "2px 10px", borderRadius: 999, fontSize: 12 };
const bandColor: Record<string, React.CSSProperties> = {
  high: { background: "#d1fae5", color: "#059669" },
  medium: { background: "#fef3c7", color: "#92600a" },
  low: { background: "#fee2e2", color: "#dc2626" },
};
const resumeColor: Record<string, React.CSSProperties> = {
  none: { background: "#f1f3f5", color: "#6b7280" },
  pending: { background: "#fef3c7", color: "#92600a" },
  done: { background: "#d1fae5", color: "#059669" },
  failed: { background: "#fee2e2", color: "#dc2626" },
};
const btnSm: React.CSSProperties = {
  padding: "4px 10px", border: "none", borderRadius: 8,
  background: "#4338ca", color: "#fff", cursor: "pointer", fontSize: 12,
};
const sub: React.CSSProperties = { color: "#6b7280", fontSize: 12 };
const confirmRow: React.CSSProperties = {
  background: "#fffbeb", borderTop: "1px solid #fde68a",
  borderBottom: "1px solid #fde68a", fontSize: 13,
};
