export default function Home() {
  return (
    <main style={{ maxWidth: 560, margin: "12vh auto 0", textAlign: "center" }}>
      <h1>HAS — Hiring Automation System</h1>
      <p style={{ color: "#666" }}>
        Apply for open positions, or sign in to manage recruitment.
      </p>
      <p style={{ display: "flex", gap: 16, justifyContent: "center", marginTop: 32 }}>
        <a href="/apply" style={primary}>Apply for a position</a>
        <a href="/login" style={secondary}>Staff sign in</a>
      </p>
    </main>
  );
}

const primary: React.CSSProperties = {
  padding: "12px 24px", borderRadius: 8, background: "#334",
  color: "#fff", textDecoration: "none",
};
const secondary: React.CSSProperties = {
  padding: "12px 24px", borderRadius: 8, border: "1px solid #ccc",
  color: "#334", textDecoration: "none",
};
