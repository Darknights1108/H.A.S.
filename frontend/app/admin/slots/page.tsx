"use client";

import { useCallback, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Interviewer = { id: string; name: string; email: string };
type SlotRow = {
  id: string; date: string; start: string; end: string; status: string;
  interviewers: { id: string; name: string }[];
};

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10);
}

export default function AdminSlotsPage() {
  const today = new Date();
  const in14 = new Date(today.getTime() + 14 * 86400000);
  const [startDate, setStartDate] = useState(isoDate(today));
  const [endDate, setEndDate] = useState(isoDate(in14));
  const [slots, setSlots] = useState<SlotRow[]>([]);
  const [interviewers, setInterviewers] = useState<Interviewer[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [sr, ir] = await Promise.all([
      fetch(`${API}/api/slots?start_date=${startDate}&end_date=${endDate}`),
      fetch(`${API}/api/interviewers`),
    ]);
    if (sr.ok) setSlots(await sr.json());
    if (ir.ok) {
      const list: Interviewer[] = await ir.json();
      setInterviewers(list);
      if (list.length && !selected) setSelected(list[0].id);
    }
  }, [startDate, endDate, selected]);

  useEffect(() => {
    load();
  }, [load]);

  async function api(method: string, path: string, body?: object) {
    setNotice(null);
    const r = await fetch(`${API}/api${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) setNotice(data.detail ?? `HTTP ${r.status}`);
    await load();
  }

  const byDate = slots.reduce<Record<string, SlotRow[]>>((acc, s) => {
    (acc[s.date] ??= []).push(s);
    return acc;
  }, {});

  return (
    <main style={{ maxWidth: 900 }}>
      <h1>Slots admin</h1>

      <section style={card}>
        <h2 style={{ marginTop: 0 }}>Interviewers</h2>
        <p>{interviewers.map((i) => i.name).join(", ") || "none yet"}</p>
        <input placeholder="Name" value={newName} onChange={(e) => setNewName(e.target.value)} style={input} />{" "}
        <input placeholder="Email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} style={input} />{" "}
        <button
          style={btn}
          onClick={() => {
            if (newName && newEmail) {
              api("POST", "/interviewers", { name: newName, email: newEmail });
              setNewName(""); setNewEmail("");
            }
          }}
        >
          Add interviewer
        </button>
        <p style={{ marginBottom: 0 }}>
          Acting as:{" "}
          <select value={selected} onChange={(e) => setSelected(e.target.value)} style={input}>
            {interviewers.map((i) => (
              <option key={i.id} value={i.id}>{i.name}</option>
            ))}
          </select>
        </p>
      </section>

      <section style={card}>
        <h2 style={{ marginTop: 0 }}>Slot grid</h2>
        <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} style={input} />{" "}
        →{" "}
        <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} style={input} />{" "}
        <button
          style={btn}
          onClick={() => api("POST", "/slots/generate", { start_date: startDate, end_date: endDate })}
        >
          Generate hourly slots (Mon–Fri 9–18)
        </button>
      </section>

      {notice && <p style={{ color: "#b00" }}>{notice}</p>}

      {Object.entries(byDate).map(([date, rows]) => (
        <section key={date} style={card}>
          <h3 style={{ marginTop: 0 }}>{date}</h3>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th style={th}>Time</th><th style={th}>Status</th>
                <th style={th}>Panel</th><th style={th}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => {
                const mine = s.interviewers.some((i) => i.id === selected);
                return (
                  <tr key={s.id}>
                    <td style={td}>{s.start}–{s.end}</td>
                    <td style={td}>
                      <span style={{ ...badge, ...badgeColor[s.status] }}>{s.status}</span>
                    </td>
                    <td style={td}>{s.interviewers.map((i) => i.name).join(", ") || "—"}</td>
                    <td style={td}>
                      {selected && !mine && (
                        <button style={btnSm} onClick={() => api("POST", `/slots/${s.id}/claim`, { interviewer_id: selected })}>
                          Claim
                        </button>
                      )}
                      {selected && mine && (
                        <button style={btnSm} onClick={() => api("DELETE", `/slots/${s.id}/claim/${selected}`)}>
                          Withdraw
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ))}
    </main>
  );
}

const card: React.CSSProperties = {
  border: "1px solid #ddd", borderRadius: 8, padding: "12px 16px", margin: "16px 0",
};
const input: React.CSSProperties = { padding: "6px 8px", border: "1px solid #ccc", borderRadius: 4 };
const btn: React.CSSProperties = {
  padding: "6px 14px", border: "none", borderRadius: 4, background: "#334", color: "#fff", cursor: "pointer",
};
const btnSm: React.CSSProperties = { ...btn, padding: "4px 10px" };
const th: React.CSSProperties = { textAlign: "left", borderBottom: "2px solid #ddd", padding: 6 };
const td: React.CSSProperties = { borderBottom: "1px solid #eee", padding: 6 };
const badge: React.CSSProperties = { padding: "2px 8px", borderRadius: 10, fontSize: 12 };
const badgeColor: Record<string, React.CSSProperties> = {
  empty: { background: "#eee", color: "#555" },
  open: { background: "#d8f5e8", color: "#0a6" },
  booked: { background: "#dbeafe", color: "#1d4ed8" },
};
