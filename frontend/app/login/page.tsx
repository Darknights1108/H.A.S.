"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [debugLink, setDebugLink] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    try {
      const r = await fetch(`${API}/api/auth/request-link`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await r.json().catch(() => ({}));
      setSent(true);
      if (data.debug_link) setDebugLink(data.debug_link); // 仅开发模式出现
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={wrap}>
      <h1 style={{ textAlign: "center" }}>Sign in to HAS</h1>
      {sent ? (
        <div style={card}>
          <p>
            Please check your email. If this email is allowed, a login link will
            be sent. The link expires in 15 minutes.
          </p>
          {debugLink && (
            <p style={{ fontSize: 12, color: "#888", wordBreak: "break-all" }}>
              [dev only] <a href={debugLink}>{debugLink}</a>
            </p>
          )}
          <button style={secondary} onClick={() => { setSent(false); setDebugLink(null); }}>
            Use a different email
          </button>
        </div>
      ) : (
        <div style={card}>
          <label style={{ fontWeight: 600 }}>Email address</label>
          <input
            style={input}
            type="email"
            value={email}
            placeholder="you@example.com"
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && email.includes("@") && submit()}
          />
          <p>
            <button style={primary} disabled={busy || !email.includes("@")} onClick={submit}>
              {busy ? "Sending…" : "Send me a login link"}
            </button>
          </p>
          <p style={{ color: "#888", fontSize: 13 }}>
            No password needed — we email you a one-time sign-in link.
          </p>
        </div>
      )}
    </main>
  );
}

const wrap: React.CSSProperties = { maxWidth: 420, margin: "8vh auto 0" };
const card: React.CSSProperties = {
  border: "1px solid #ddd", borderRadius: 8, padding: "20px 24px",
};
const input: React.CSSProperties = {
  display: "block", width: "100%", padding: "10px 12px", marginTop: 6,
  border: "1px solid #ccc", borderRadius: 6, boxSizing: "border-box",
};
const primary: React.CSSProperties = {
  padding: "10px 20px", border: "none", borderRadius: 6,
  background: "#334", color: "#fff", cursor: "pointer",
};
const secondary: React.CSSProperties = {
  padding: "8px 16px", border: "1px solid #ccc", borderRadius: 6,
  background: "#f5f5f5", cursor: "pointer",
};
