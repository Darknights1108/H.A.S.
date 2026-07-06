"use client";

import { useCallback, useEffect, useState } from "react";
import AdminBar from "@/components/AdminBar";
import { API, useSession } from "@/lib/session";

type ResumeRow = {
  application_id: string;
  candidate_name: string;
  candidate_email: string;
  job_title: string;
  file_ext: string;
  parse_status: "none" | "pending" | "done" | "failed";
  application_status: string;
  submitted_at: string;
};

export default function ResumesPage() {
  const { session, loading } = useSession(false); // interviewer + admin
  const [rows, setRows] = useState<ResumeRow[]>([]);

  const load = useCallback(async () => {
    const r = await fetch(`${API}/api/resumes`);
    if (r.ok) setRows(await r.json());
  }, []);

  useEffect(() => {
    if (session) load();
  }, [session, load]);

  if (loading || !session) return <main><p>Loading…</p></main>;

  return (
    <main style={{ maxWidth: 900 }}>
      <AdminBar session={session} />
      <h1>Resumes</h1>
      <p style={{ color: "#6b7280" }}>
        All uploaded candidate resumes. View opens in the browser (PDF/TXT);
        Download saves the original file.
      </p>

      {rows.length === 0 && <p>No resumes uploaded yet.</p>}
      {rows.length > 0 && (
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr>
              <th style={th}>Candidate</th><th style={th}>Job</th>
              <th style={th}>File</th><th style={th}>Parse</th>
              <th style={th}>Uploaded</th><th style={th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.application_id}>
                <td style={td}>
                  {r.candidate_name}
                  <div style={sub}>{r.candidate_email}</div>
                </td>
                <td style={td}>
                  {r.job_title}
                  <div style={sub}>{r.application_status}</div>
                </td>
                <td style={td}>
                  <span style={{ ...badge, background: "#e0e7ff", color: "#4338ca" }}>
                    {r.file_ext.toUpperCase()}
                  </span>
                </td>
                <td style={td}>
                  <span style={{ ...badge, ...parseColor[r.parse_status] }}>
                    {r.parse_status === "done" ? "parsed ✓" : r.parse_status}
                  </span>
                </td>
                <td style={td}>{r.submitted_at.slice(0, 10)}</td>
                <td style={{ ...td, whiteSpace: "nowrap" }}>
                  <a
                    style={{ ...btnSm, textDecoration: "none", display: "inline-block" }}
                    href={`${API}/api/applications/${r.application_id}/resume?inline=true`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View
                  </a>{" "}
                  <a
                    style={{ ...btnSm, background: "#059669", textDecoration: "none", display: "inline-block" }}
                    href={`${API}/api/applications/${r.application_id}/resume`}
                  >
                    Download
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

const th: React.CSSProperties = { textAlign: "left", borderBottom: "2px solid #e5e7eb", padding: 8 };
const td: React.CSSProperties = { borderBottom: "1px solid #f1f3f5", padding: 8, verticalAlign: "top" };
const sub: React.CSSProperties = { color: "#6b7280", fontSize: 12 };
const badge: React.CSSProperties = { padding: "2px 10px", borderRadius: 999, fontSize: 12 };
const parseColor: Record<string, React.CSSProperties> = {
  none: { background: "#f1f3f5", color: "#6b7280" },
  pending: { background: "#fef3c7", color: "#92600a" },
  done: { background: "#d1fae5", color: "#059669" },
  failed: { background: "#fee2e2", color: "#dc2626" },
};
const btnSm: React.CSSProperties = {
  padding: "4px 10px", border: "none", borderRadius: 8,
  background: "#4338ca", color: "#fff", cursor: "pointer", fontSize: 12,
};
