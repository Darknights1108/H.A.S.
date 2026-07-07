"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function LoginPage() {
  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [debugCode, setDebugCode] = useState<string | null>(null);

  async function sendCode() {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${API}/api/auth/request-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await r.json().catch(() => ({}));
      setInfo(data.message ?? "If this email is allowed, a code has been sent.");
      if (data.debug_code) setDebugCode(data.debug_code); // dev mode only
      setCode("");
      setStep("code");
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${API}/api/auth/verify-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code }),
      });
      const data = await r.json();
      if (!r.ok) {
        setError(data.detail ?? `HTTP ${r.status}`);
        return;
      }
      window.location.href =
        data.role === "admin" ? "/admin/applications" : "/admin/slots";
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={wrap}>
      <h1 style={{ textAlign: "center" }}>Sign in to HAS</h1>

      {step === "email" && (
        <div style={card}>
          <label style={{ fontWeight: 600 }}>Email address</label>
          <input
            style={input}
            type="email"
            value={email}
            placeholder="you@example.com"
            autoFocus
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && email.includes("@") && sendCode()}
          />
          <p>
            <button style={primary} disabled={busy || !email.includes("@")} onClick={sendCode}>
              {busy ? "Sending…" : "Send Code"}
            </button>
          </p>
          <p style={{ color: "#6b7280", fontSize: 13 }}>
            No password needed — we email you a one-time verification code.
          </p>
        </div>
      )}

      {step === "code" && (
        <div style={card}>
          <p style={{ marginTop: 0, color: "#374151", fontSize: 14 }}>
            {info}
          </p>
          <p style={{ color: "#6b7280", fontSize: 13, margin: "4px 0 12px" }}>
            Sent to <b>{email}</b> · expires in 10 minutes
          </p>
          {debugCode && (
            <p style={{ fontSize: 12, color: "#6b7280" }}>
              [dev only] code: <b>{debugCode}</b>
            </p>
          )}
          <label style={{ fontWeight: 600 }}>Verification code</label>
          <input
            style={{ ...input, letterSpacing: 8, fontSize: 22, textAlign: "center", fontWeight: 600 }}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            placeholder="••••••"
            autoFocus
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            onKeyDown={(e) => e.key === "Enter" && code.length === 6 && verify()}
          />
          {error && (
            <p style={{ background: "#fee2e2", border: "1px solid #fecaca", borderRadius: 8,
                        padding: "8px 12px", color: "#dc2626", fontSize: 13 }}>
              ⚠ {error}
            </p>
          )}
          <p>
            <button style={primary} disabled={busy || code.length !== 6} onClick={verify}>
              {busy ? "Verifying…" : "Verify"}
            </button>
          </p>
          <p style={{ fontSize: 13 }}>
            <button style={linkBtn} disabled={busy} onClick={sendCode}>
              Resend code
            </button>
            {" · "}
            <button
              style={linkBtn}
              disabled={busy}
              onClick={() => { setStep("email"); setError(null); setDebugCode(null); }}
            >
              Use a different email
            </button>
          </p>
        </div>
      )}
    </main>
  );
}

const wrap: React.CSSProperties = { maxWidth: 420, margin: "8vh auto 0" };
const card: React.CSSProperties = {
  background: "#fff", boxShadow: "0 1px 3px rgba(16,24,40,0.06)",
  border: "1px solid #e5e7eb", borderRadius: 12, padding: "20px 24px",
};
const input: React.CSSProperties = {
  display: "block", width: "100%", padding: "10px 12px", marginTop: 6,
  border: "1px solid #d1d5db", borderRadius: 8, boxSizing: "border-box",
};
const primary: React.CSSProperties = {
  padding: "10px 20px", border: "none", borderRadius: 8,
  background: "#4338ca", color: "#fff", cursor: "pointer",
};
const linkBtn: React.CSSProperties = {
  border: "none", background: "none", color: "#4338ca",
  cursor: "pointer", textDecoration: "underline", padding: 0, fontSize: 13,
};
