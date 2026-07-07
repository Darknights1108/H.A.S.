"use client";

import { useEffect, useState } from "react";
import AdminBar from "@/components/AdminBar";
import { API, useSession } from "@/lib/session";

type Analytics = {
  overview: {
    total_applications: number; total_candidates: number; open_jobs: number;
    offers: number; avg_days_to_book: number | null;
  };
  funnel: { stage: string; count: number }[];
  bands: Record<"high" | "medium" | "low", number>;
  rejection_reasons: Record<string, number>;
  per_job: { title: string; applications: number; passed: number }[];
  daily_applications: { date: string; count: number }[];
  slots: { open: number; booked: number; empty: number };
  interviewer_load: { name: string; claimed: number; booked: number }[];
};

export default function AnalyticsPage() {
  const { session, loading } = useSession(true);
  const [data, setData] = useState<Analytics | null>(null);

  useEffect(() => {
    if (session) {
      fetch(`${API}/api/analytics`).then(async (r) => {
        if (r.ok) setData(await r.json());
      });
    }
  }, [session]);

  if (loading || !session) return <main><p>Loading…</p></main>;
  if (!data) return <main style={{ maxWidth: 960 }}><AdminBar session={session} /><p>Loading analytics…</p></main>;

  const { overview, funnel, bands, rejection_reasons, per_job, daily_applications, slots, interviewer_load } = data;
  const funnelMax = Math.max(1, ...funnel.map((f) => f.count));
  const bandTotal = Math.max(1, bands.high + bands.medium + bands.low);
  const dailyMax = Math.max(1, ...daily_applications.map((d) => d.count));
  const slotTotal = Math.max(1, slots.open + slots.booked + slots.empty);

  return (
    <main style={{ maxWidth: 960 }}>
      <AdminBar session={session} />
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <h1 style={{ flex: 1 }}>Analytics</h1>
        <a
          href={`${API}/api/analytics/export`}
          style={{
            padding: "8px 18px", borderRadius: 8, background: "#059669",
            color: "#fff", textDecoration: "none", fontSize: 14,
          }}
        >
          ⬇ Export to Excel
        </a>
      </div>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <Card label="Applications" value={overview.total_applications} />
        <Card label="Candidates" value={overview.total_candidates} />
        <Card label="Open jobs" value={overview.open_jobs} />
        <Card label="Offers (passed)" value={overview.offers} />
        <Card label="Avg days to book" value={overview.avg_days_to_book ?? "—"} />
      </div>

      <section style={card}>
        <h2 style={h2}>Hiring funnel</h2>
        {funnel.map((f) => (
          <div key={f.stage} style={{ display: "flex", alignItems: "center", margin: "6px 0" }}>
            <span style={{ width: 260, fontSize: 13 }}>{f.stage}</span>
            <div style={{ flex: 1, background: "#eef0f3", borderRadius: 8, height: 22 }}>
              <div style={{
                width: `${(f.count / funnelMax) * 100}%`, minWidth: f.count > 0 ? 28 : 0,
                background: "#4338ca", borderRadius: 8, height: 22,
                color: "#fff", fontSize: 12, display: "flex",
                alignItems: "center", justifyContent: "flex-end", paddingRight: 6,
                boxSizing: "border-box",
              }}>
                {f.count > 0 ? f.count : ""}
              </div>
            </div>
            {f.count === 0 && <span style={{ marginLeft: 6, fontSize: 12, color: "#6b7280" }}>0</span>}
          </div>
        ))}
      </section>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <section style={{ ...card, flex: 1, minWidth: 300 }}>
          <h2 style={h2}>Screening bands</h2>
          {(["high", "medium", "low"] as const).map((b) => (
            <Bar key={b} label={b} count={bands[b]} total={bandTotal}
                 color={{ high: "#059669", medium: "#d97706", low: "#dc2626" }[b]} />
          ))}
        </section>

        <section style={{ ...card, flex: 1, minWidth: 300 }}>
          <h2 style={h2}>Rejection reasons</h2>
          {Object.keys(rejection_reasons).length === 0 && <p style={{ fontSize: 13 }}>none</p>}
          {Object.entries(rejection_reasons).sort((a, b) => b[1] - a[1]).map(([reason, n]) => (
            <Bar key={reason} label={reason} count={n}
                 total={Math.max(1, ...Object.values(rejection_reasons))} color="#6b7280" />
          ))}
        </section>
      </div>

      <section style={card}>
        <h2 style={h2}>Applications — last 14 days</h2>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 90 }}>
          {daily_applications.map((d) => (
            <div key={d.date} title={`${d.date}: ${d.count}`}
                 style={{ flex: 1, textAlign: "center", fontSize: 10, color: "#6b7280" }}>
              <div style={{
                height: Math.round((d.count / dailyMax) * 70),
                background: d.count ? "#4338ca" : "#f1f3f5", borderRadius: 3,
              }} />
              {d.date.slice(8)}
            </div>
          ))}
        </div>
      </section>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <section style={{ ...card, flex: 1, minWidth: 300 }}>
          <h2 style={h2}>Per job</h2>
          <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
            <thead><tr><th style={th}>Job</th><th style={th}>Apps</th><th style={th}>Passed</th></tr></thead>
            <tbody>
              {per_job.map((j) => (
                <tr key={j.title}>
                  <td style={td}>{j.title}</td>
                  <td style={td}>{j.applications}</td>
                  <td style={td}>{j.passed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section style={{ ...card, flex: 1, minWidth: 300 }}>
          <h2 style={h2}>Upcoming slots</h2>
          <Bar label={`open (${slots.open})`} count={slots.open} total={slotTotal} color="#059669" />
          <Bar label={`booked (${slots.booked})`} count={slots.booked} total={slotTotal} color="#1d4ed8" />
          <Bar label={`empty (${slots.empty})`} count={slots.empty} total={slotTotal} color="#bbb" />
          <h2 style={{ ...h2, marginTop: 16 }}>Interviewer load</h2>
          <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
            <thead><tr><th style={th}>Interviewer</th><th style={th}>Claimed</th><th style={th}>Booked</th></tr></thead>
            <tbody>
              {interviewer_load.map((i) => (
                <tr key={i.name}>
                  <td style={td}>{i.name}</td>
                  <td style={td}>{i.claimed}</td>
                  <td style={td}>{i.booked}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </main>
  );
}

function Card({ label, value }: { label: string; value: number | string }) {
  return (
    <div style={{ ...card, flex: 1, minWidth: 130, textAlign: "center", margin: 0 }}>
      <div style={{ fontSize: 26, fontWeight: 700 }}>{value}</div>
      <div style={{ fontSize: 12, color: "#6b7280" }}>{label}</div>
    </div>
  );
}

function Bar({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", margin: "6px 0" }}>
      <span style={{ width: 130, fontSize: 13 }}>{label}</span>
      <div style={{ flex: 1, background: "#eef0f3", borderRadius: 8, height: 18 }}>
        <div style={{ width: `${(count / total) * 100}%`, background: color, borderRadius: 8, height: 18 }} />
      </div>
      <span style={{ width: 36, textAlign: "right", fontSize: 13 }}>{count}</span>
    </div>
  );
}

const card: React.CSSProperties = {
  background: "#fff", boxShadow: "0 1px 3px rgba(16,24,40,0.06)", border: "1px solid #e5e7eb", borderRadius: 12, padding: "12px 16px", margin: "16px 0",
};
const h2: React.CSSProperties = { marginTop: 0, fontSize: 16 };
const th: React.CSSProperties = { textAlign: "left", borderBottom: "2px solid #e5e7eb", padding: 6 };
const td: React.CSSProperties = { borderBottom: "1px solid #f1f3f5", padding: 6 };
