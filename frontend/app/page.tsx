"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Setting = { key: string; value: unknown; description: string | null };

export default function Home() {
  const [settings, setSettings] = useState<Setting[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/api/settings`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: Setting[]) => setSettings(data))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main style={{ maxWidth: 720 }}>
      <h1>HAS — Hiring Automation System</h1>
      <p style={{ color: "#666" }}>
        最小闭环:前端从后端 <code>{API}/api/settings</code> 拉取配置。
      </p>

      {loading && <p>Loading…</p>}
      {error && (
        <p style={{ color: "#b00" }}>
          连接后端失败:{error}（确认后端已在 {API} 运行）
        </p>
      )}

      {!loading && !error && (
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr>
              <th style={th}>Key</th>
              <th style={th}>Value</th>
              <th style={th}>Description</th>
            </tr>
          </thead>
          <tbody>
            {settings.map((s) => (
              <tr key={s.key}>
                <td style={td}><code>{s.key}</code></td>
                <td style={td}>{JSON.stringify(s.value)}</td>
                <td style={td}>{s.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

const th: React.CSSProperties = {
  textAlign: "left",
  borderBottom: "2px solid #ddd",
  padding: "8px",
};
const td: React.CSSProperties = {
  borderBottom: "1px solid #eee",
  padding: "8px",
};
