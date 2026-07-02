"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

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

const WEEKDAY_HEADERS = ["S", "M", "T", "W", "T", "F", "S"];

function pad(n: number) {
  return String(n).padStart(2, "0");
}

/** 本月月历(固定,不可翻月):工作日且有空档才可选 */
function MonthCalendar({
  openDates,
  activeDate,
  onPick,
}: {
  openDates: Set<string>;
  activeDate: string | null;
  onPick: (d: string) => void;
}) {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth(); // 0-based
  const todayKey = `${year}-${pad(month + 1)}-${pad(now.getDate())}`;
  const firstWeekday = new Date(year, month, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const monthLabel = now.toLocaleString("en-US", { month: "long", year: "numeric" });

  const cells: (number | null)[] = [
    ...Array<null>(firstWeekday).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  return (
    <div style={{ maxWidth: 340 }}>
      <p style={{ fontWeight: 600, margin: "0 0 8px" }}>{monthLabel}</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
        {WEEKDAY_HEADERS.map((h, i) => (
          <div key={i} style={{ textAlign: "center", color: "#888", fontSize: 12, padding: 4 }}>
            {h}
          </div>
        ))}
        {cells.map((d, i) => {
          if (d === null) return <div key={`pad-${i}`} />;
          const key = `${year}-${pad(month + 1)}-${pad(d)}`;
          const weekday = new Date(year, month, d).getDay();
          const isWeekend = weekday === 0 || weekday === 6;
          const isPast = key < todayKey;
          const available = openDates.has(key) && !isWeekend && !isPast;
          const isActive = key === activeDate;
          return (
            <button
              key={key}
              disabled={!available}
              onClick={() => onPick(key)}
              style={{
                padding: "8px 0",
                borderRadius: "50%",
                border: "none",
                fontSize: 13,
                cursor: available ? "pointer" : "default",
                background: isActive ? "#334" : available ? "#eef" : "transparent",
                color: isActive ? "#fff" : available ? "#334" : isWeekend || isPast ? "#ccc" : "#999",
                fontWeight: available ? 600 : 400,
              }}
            >
              {d}
            </button>
          );
        })}
      </div>
      <p style={{ color: "#888", fontSize: 12 }}>Interviews are held on working days (Mon–Fri) only.</p>
    </div>
  );
}

export default function BookingPage() {
  const { token } = useParams<{ token: string }>();
  const [state, setState] = useState<BookingState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeDate, setActiveDate] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [details, setDetails] = useState({ name: "", email: "", phone: "" });
  const [showReschedule, setShowReschedule] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/booking/${token}`);
      if (!r.ok) throw new Error(r.status === 404 ? "Booking link not found" : `HTTP ${r.status}`);
      const data: BookingState = await r.json();
      setState(data);
      setDetails({
        name: data.candidate.name ?? "",
        email: data.candidate.email ?? "",
        phone: data.candidate.phone ?? "",
      });
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

  const openDates = useMemo(
    () => new Set(state?.open_slots.map((s) => s.date) ?? []),
    [state]
  );

  useEffect(() => {
    if (openDates.size && (activeDate === null || !openDates.has(activeDate))) {
      setActiveDate([...openDates].sort()[0]);
    }
  }, [openDates, activeDate]);

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
      if (!r.ok) setNotice(data.detail ?? `HTTP ${r.status}`);
      else if (path === "reschedule") setShowReschedule(false); // 改期成功后收起日历
      await load();
    } catch (e) {
      setNotice(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <main style={wrap}><p style={{ color: "#b00" }}>{error}</p></main>;
  if (!state) return <main style={wrap}><p>Loading…</p></main>;

  const { held_slot, confirmed, interview, open_slots } = state;
  const canReschedule =
    confirmed && interview &&
    (interview.reschedule_max <= 0 || interview.reschedule_count < interview.reschedule_max);
  const pickable = !confirmed || (canReschedule && showReschedule);
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
          {interview.reschedule_max > 0 && (
            <p style={{ color: "#666" }}>
              Reschedules used: {interview.reschedule_count}/{interview.reschedule_max}
            </p>
          )}
          {canReschedule && (
            <p>
              <button
                style={secondary}
                onClick={() => setShowReschedule((v) => !v)}
              >
                {showReschedule ? "Cancel reschedule" : "Reschedule"}
              </button>
            </p>
          )}
        </section>
      )}

      {notice && <p style={{ color: "#b00" }}>{notice}</p>}

      {pickable && (
        <section>
          <h2>{confirmed ? "Reschedule — pick a new time" : "Pick a time"}</h2>
          {open_slots.length === 0 && !held_slot && (
            <p>No open slots right now — please check back later.</p>
          )}
          <div style={{ display: "flex", gap: 32, flexWrap: "wrap" }}>
            <MonthCalendar openDates={openDates} activeDate={activeDate} onPick={setActiveDate} />
            <div style={{ flex: 1, minWidth: 220 }}>
              {activeDate && <p style={{ fontWeight: 600, margin: "0 0 8px" }}>{activeDate}</p>}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
                {held_slot && !confirmed && (
                  <button style={timeActive} disabled>
                    {held_slot.date === activeDate ? held_slot.start : `${held_slot.date} ${held_slot.start}`} ✓
                  </button>
                )}
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
              {held_slot && !confirmed && (
                <p style={{ color: "#666", fontSize: 13 }}>
                  Selected: {held_slot.date} {held_slot.start}–{held_slot.end}{" "}
                  <button style={linkBtn} disabled={busy} onClick={() => act("withdraw")}>
                    withdraw
                  </button>
                </p>
              )}
            </div>
          </div>
        </section>
      )}

      {!confirmed && held_slot && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Add your details</h2>
          <label style={lbl}>First and last name *</label>
          <input style={input} value={details.name}
            onChange={(e) => setDetails({ ...details, name: e.target.value })} />
          <label style={lbl}>Email *</label>
          <input style={input} type="email" value={details.email}
            onChange={(e) => setDetails({ ...details, email: e.target.value })} />
          <label style={lbl}>Phone number *</label>
          <input style={input} value={details.phone}
            onChange={(e) => setDetails({ ...details, phone: e.target.value })} />
          <p>
            <button
              style={primary}
              disabled={busy || !details.name.trim() || !details.email.trim() || !details.phone.trim()}
              onClick={() => act("confirm", details)}
            >
              {busy ? "Booking…" : "Confirm booking"}
            </button>
          </p>
        </section>
      )}
    </main>
  );
}

const wrap: React.CSSProperties = { maxWidth: 720, margin: "0 auto" };
const card: React.CSSProperties = {
  border: "1px solid #ddd", borderRadius: 8, padding: "12px 16px", margin: "16px 0",
};
const lbl: React.CSSProperties = { display: "block", marginTop: 12, fontWeight: 600 };
const input: React.CSSProperties = {
  display: "block", width: "100%", maxWidth: 420, padding: "8px 10px", marginTop: 4,
  border: "1px solid #ccc", borderRadius: 6, boxSizing: "border-box",
};
const timeBtn: React.CSSProperties = {
  padding: "10px 0", border: "1px solid #ccc", borderRadius: 6, background: "#fff", cursor: "pointer",
};
const timeActive: React.CSSProperties = { ...timeBtn, background: "#334", color: "#fff", border: "none" };
const primary: React.CSSProperties = {
  padding: "10px 22px", border: "none", borderRadius: 6, background: "#334", color: "#fff", cursor: "pointer",
};
const linkBtn: React.CSSProperties = {
  border: "none", background: "none", color: "#06c", cursor: "pointer", textDecoration: "underline", padding: 0,
};
const joinBtn: React.CSSProperties = {
  display: "inline-block", padding: "10px 18px", borderRadius: 6,
  background: "#0a7", color: "#fff", textDecoration: "none",
};
