"use client";

import { usePathname } from "next/navigation";
import { logout, Session } from "@/lib/session";

const LINKS: [string, string, boolean][] = [
  // [href, label, adminOnly]
  ["/admin/applications", "Applications", true],
  ["/admin/jobs", "Jobs", true],
  ["/admin/slots", "Slots", false],
  ["/admin/emails", "Emails", true],
  ["/admin/allowlist", "Allowlist", true],
  ["/admin/analytics", "Analytics", true],
  ["/admin/settings", "Settings", true],
];

export default function AdminBar({ session }: { session: Session }) {
  const path = usePathname();
  return (
    <nav style={bar}>
      <span style={brand}>HAS</span>
      {LINKS.filter(([, , adminOnly]) => !adminOnly || session.role === "admin").map(
        ([href, label]) => (
          <a key={href} href={href} style={path === href ? linkActive : link}>
            {label}
          </a>
        )
      )}
      <span style={{ marginLeft: "auto", color: "#6b7280", fontSize: 13 }}>
        {session.email}
        <span style={roleChip}>{session.role}</span>
      </span>
      <button style={logoutBtn} onClick={logout}>
        Logout
      </button>
    </nav>
  );
}

const bar: React.CSSProperties = {
  position: "sticky", top: 12, zIndex: 20,
  display: "flex", alignItems: "center", gap: 4,
  background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12,
  boxShadow: "0 1px 3px rgba(16,24,40,0.08)",
  padding: "8px 14px", marginBottom: 20,
};
const brand: React.CSSProperties = {
  fontWeight: 800, letterSpacing: "-0.02em", marginRight: 10,
  color: "#4338ca",
};
const link: React.CSSProperties = {
  color: "#374151", textDecoration: "none", fontSize: 13.5,
  padding: "6px 10px", borderRadius: 8,
};
const linkActive: React.CSSProperties = {
  ...link, background: "#eef2ff", color: "#4338ca", fontWeight: 600,
};
const roleChip: React.CSSProperties = {
  marginLeft: 6, padding: "1px 8px", borderRadius: 999,
  background: "#eef2ff", color: "#4338ca", fontSize: 11, fontWeight: 600,
};
const logoutBtn: React.CSSProperties = {
  marginLeft: 10, padding: "5px 12px", border: "1px solid #e5e7eb",
  borderRadius: 8, background: "#fff", color: "#374151", fontSize: 13,
};
