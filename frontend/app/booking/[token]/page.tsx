"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type SlotView = { id: string; date: string; start: string; end: string; interviewers: string[] };
type BookingState = {
  candidate: { name: string; email: string; phone: string | null };
  application_status: string;
  held_slot: SlotView | null;
  confirmed: boolean;
  interview: { meeting_link: string; reschedule_count: number; reschedule_max: number } | null;
  open_slots: SlotView[];
  timezone: string;
};

export default function BookingPage() {
  const { token } = useParams<{ token: string }>();
  const [state, setState] = useState<BookingState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeDate, setActiveDate] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/booking/${token}`);
      if (!r.ok) throw new Error(r.status === 404 ? "Booking link not found" : `HTTP ${r.status}`);
      const data: BookingState = await r.json();
      setState(data);
      setError(null);
      return data;
    } catch (e) {
      setError(String(e));
      return null;
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const dates = useMemo(() => {
    if (!state) return [];
    return Array.from(new Set(state.open_slots.map((s) => s.date))).sort();
  }, [state]);

  useEffect(() => {
    if (dates.length && (activeDate === null || !dates.includes(activeDate))) {
      setActiveDate(dates[0]);
    }
  }, [dates, activeDate]);

  async function act(path: string, body?: object) {
    setBusy(true);
    setNotice(null);
    try {
      const r = await fetch(`${API}/api/booking/${token}/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await r.json();
      if (!r.ok) {
        setNotice(data.detail ?? `HTTP ${r.status}`);
      }
      await load();
    } catch (e) {
      setNotice(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <main style={wrap}><p style={{ color: "#b00" }}>{error}</p></main>;
  if (!state) return <main style={wrap}><p>Loading…</p></main>;

  const { candidate, held_slot, confirmed, interview, open_slots } = state;
  const canReschedule =
    confirmed && interview && interview.reschedule_count < interview.reschedule_max;
  const pickable = !confirmed || canReschedule;
  const daySlots = open_slots.filter((s) => s.date === activeDate);

  return (
    <main style={wrap}>
      <h1 style={{ textAlign: "center" }}>Internship Interview</h1>
      <p style={{ textAlign: "center", color: "#666" }}>{state.timezone}</p>

      {confirmed && interview && held_slot && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Your booking is confirmed ✅</h2>
          <p><b>When:</b> {held_slot.date} {held_slot.start}–{held_slot.end}</p>
          <p><b>With:</b> {held_slot.interviewers.join(", ") || "TBA"}</p>
          <p>
            <a href={interview.meeting_link} target="_blank" rel="noreferrer" style={joinBtn}>
              Join your appointment
            </a>
          </p>
          <p style={{ color: "#666" }}>
            Reschedules used: {interview.reschedule_count}/{interview.reschedule_max}
            {canReschedule && " — pick a new time below to reschedule."}
          </p>
        </section>
      )}

      {!confirmed && held_slot && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Selected time (not confirmed yet)</h2>
          <p>
            <b>{held_slot.date} {held_slot.start}–{held_slot.end}</b>
            {"  with "}{held_slot.interviewers.join(", ")}
          </p>
          <button style={primary} disabled={busy} onClick={() => act("confirm")}>
            Confirm booking
          </button>{" "}
          <button style={secondary} disabled={busy} onClick={() => act("withdraw")}>
            Withdraw &amp; pick another
          </button>
        </section>
      )}

      {notice && <p style={{ color: "#b00" }}>{notice}</p>}

      {pickable && (
        <section>
          <h2>{confirmed ? "Reschedule — pick a new time" : "Pick a time"}</h2>
          {dates.length === 0 && <p>No open slots right now — please check back later.</p>}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
            {dates.map((d) => (
              <button
                key={d}
                style={d === activeDate ? dateActive : dateBtn}
                onClick={() => setActiveDate(d)}
              >
                {d}
              </button>
            ))}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, maxWidth: 480 }}>
            {daySlots.map((s) => (
              <button
                key={s.id}
                style={timeBtn}
                disabled={busy}
                title={`Panel: ${s.interviewers.join(", ")}`}
                onClick={() =>
                  confirmed
                    ? act("reschedule", { slot_id: s.id })
                    : act("select", { slot_id: s.id })
                }
              >
                {s.start}
              </button>
            ))}
          </div>
        </section>
      )}

      <section style={{ ...card, marginTop: 24 }}>
        <h2 style={{ marginTop: 0 }}>Your details</h2>
        <p><b>Name:</b> {candidate.name}</p>
        <p><b>Email:</b> {candidate.email}</p>
        <p><b>Phone:</b> {candidate.phone ?? "—"}</p>
      </section>
    </main>
  );
}

const wrap: React.CSSProperties = { maxWidth: 640, margin: "0 auto" };
const card: React.CSSProperties = {
  border: "1px solid #ddd", borderRadius: 8, padding: "12px 16px", margin: "16px 0",
};
const dateBtn: React.CSSProperties = {
  padding: "8px 12px", border: "1px solid #ccc", borderRadius: 6, background: "#fff", cursor: "pointer",
};
const dateActive: React.CSSProperties = { ...dateBtn, background: "#334", color: "#fff" };
const timeBtn: React.CSSProperties = {
  padding: "10px 0", border: "1px solid #ccc", borderRadius: 6, background: "#fff", cursor: "pointer",
};
const primary: React.CSSProperties = {
  padding: "10px 18px", border: "none", borderRadius: 6, background: "#334", color: "#fff", cursor: "pointer",
};
const secondary: React.CSSProperties = {
  padding: "10px 18px", border: "1px solid #ccc", borderRadius: 6, background: "#f5f5f5", cursor: "pointer",
};
const joinBtn: React.CSSProperties = {
  display: "inline-block", padding: "10px 18px", borderRadius: 6,
  background: "#0a7", color: "#fff", textDecoration: "none",
};
