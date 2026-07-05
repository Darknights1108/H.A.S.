"use client";

import { useCallback, useEffect, useState } from "react";
import AdminBar from "@/components/AdminBar";
import { API, useSession } from "@/lib/session";

type Entry = {
  id: string; email: string; name: string | null; role: string;
  enabled: boolean; added_by: string | null; added_at: string;
  verified_at: string | null;
};

const ROLES = ["admin", "interviewer", "lecturer", "supervisor", "user"];

export default function AllowlistPage() {
  const { session, loading } = useSession(true);
  const [rows, setRows] = useState<Entry[]>([]);
  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState("interviewer");
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch(`${API}/api/auth/allowlist`);
    if (r.ok) setRows(await r.json());
  }, []);

  useEffect(() => {
    if (session) load();
  }, [session, load]);

  async function api(method: string, path: string, body?: object) {
    setNotice(null);
    const r = await fetch(`${API}/api/auth${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) setNotice(data.detail ?? `HTTP ${r.status}`);
    await load();
  }

  if (loading || !session) return <main><p>Loading…</p></main>;

  return (
    <main style={{ maxWidth: 900 }}>
      <AdminBar session={session} />
      <h1>Allowed emails</h1>
      <p style={{ color: "#6b7280" }}>
        只有名单内且 enabled 的邮箱才能收到登录链接。禁用/移除会立即吊销该邮箱的会话。
      </p>
      {notice && <p style={{ color: "#dc2626" }}>{notice}</p>}

      <section style={card}>
        <b>Add email</b>{" "}
        <input style={input} placeholder="email" value={newEmail}
          onChange={(e) => setNewEmail(e.target.value)} />{" "}
        <input style={input} placeholder="name (optional)" value={newName}
          onChange={(e) => setNewName(e.target.value)} />{" "}
        <select style={input} value={newRole} onChange={(e) => setNewRole(e.target.value)}>
          {ROLES.map((r) => <option key={r}>{r}</option>)}
        </select>{" "}
        <button
          style={btn}
          disabled={!newEmail.includes("@")}
          onClick={() => {
            api("POST", "/allowlist", { email: newEmail, name: newName || null, role: newRole });
            setNewEmail(""); setNewName("");
          }}
        >
          Add
        </button>
      </section>

      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th style={th}>Email</th><th style={th}>Role</th><th style={th}>Status</th>
            <th style={th}>Verified</th><th style={th}>Added</th><th style={th}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td style={td}>
                {r.email}
                {r.name && <div style={{ color: "#6b7280", fontSize: 12 }}>{r.name}</div>}
              </td>
              <td style={td}>
                <select
                  style={{ ...input, padding: "4px 6px" }}
                  value={r.role}
                  onChange={(e) => api("PATCH", `/allowlist/${r.id}`, { role: e.target.value })}
                >
                  {ROLES.map((x) => <option key={x}>{x}</option>)}
                </select>
              </td>
              <td style={td}>
                <span style={{ ...badge, background: r.enabled ? "#d1fae5" : "#fee2e2", color: r.enabled ? "#059669" : "#dc2626" }}>
                  {r.enabled ? "enabled" : "disabled"}
                </span>
              </td>
              <td style={td}>{r.verified_at ? "✓ " + r.verified_at.slice(0, 10) : "—"}</td>
              <td style={td}>
                {r.added_at.slice(0, 10)}
                <div style={{ color: "#6b7280", fontSize: 12 }}>by {r.added_by ?? "—"}</div>
              </td>
              <td style={td}>
                <button style={btnSm}
                  onClick={() => api("PATCH", `/allowlist/${r.id}`, { enabled: !r.enabled })}>
                  {r.enabled ? "Disable" : "Enable"}
                </button>{" "}
                {r.email !== session.email && (
                  <button style={{ ...btnSm, background: "#dc2626" }}
                    onClick={() => api("DELETE", `/allowlist/${r.id}`)}>
                    Remove
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}

const card: React.CSSProperties = {
  background: "#fff", boxShadow: "0 1px 3px rgba(16,24,40,0.06)", border: "1px solid #e5e7eb", borderRadius: 12, padding: "12px 16px", margin: "12px 0 20px",
};
const input: React.CSSProperties = { padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 8 };
const btn: React.CSSProperties = {
  padding: "6px 14px", border: "none", borderRadius: 8, background: "#4338ca", color: "#fff", cursor: "pointer",
};
const btnSm: React.CSSProperties = { ...btn, padding: "4px 10px", fontSize: 12 };
const th: React.CSSProperties = { textAlign: "left", borderBottom: "2px solid #e5e7eb", padding: 8 };
const td: React.CSSProperties = { borderBottom: "1px solid #f1f3f5", padding: 8, verticalAlign: "top" };
const badge: React.CSSProperties = { padding: "2px 10px", borderRadius: 999, fontSize: 12 };
