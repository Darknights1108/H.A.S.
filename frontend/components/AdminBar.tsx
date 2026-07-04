"use client";

import { logout, Session } from "@/lib/session";

const LINKS: [string, string, boolean][] = [
  // [href, label, adminOnly]
  ["/admin/applications", "Applications", true],
  ["/admin/jobs", "Jobs", true],
  ["/admin/slots", "Slots", false],
  ["/admin/emails", "Emails", true],
  ["/admin/allowlist", "Allowlist", true],
  ["/admin/settings", "Settings", true],
];

export default function AdminBar({ session }: { session: Session }) {
  return (
    <nav style={bar}>
      <span style={{ fontWeight: 700 }}>HAS</span>
      {LINKS.filter(([, , adminOnly]) => !adminOnly || session.role === "admin").map(
        ([href, label]) => (
          <a key={href} href={href} style={link}>
            {label}
          </a>
        )
      )}
      <span style={{ marginLeft: "auto", color: "#666", fontSize: 13 }}>
        {session.email} ({session.role})
      </span>
      <button style={btn} onClick={logout}>
        Logout
      </button>
    </nav>
  );
}

const bar: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 16,
  padding: "10px 0", borderBottom: "1px solid #ddd", marginBottom: 16,
};
const link: React.CSSProperties = { color: "#334", textDecoration: "none", fontSize: 14 };
const btn: React.CSSProperties = {
  padding: "4px 12px", border: "1px solid #ccc", borderRadius: 4,
  background: "#f5f5f5", cursor: "pointer", fontSize: 13,
};
