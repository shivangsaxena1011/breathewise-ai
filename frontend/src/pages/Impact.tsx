import { useMemo, useState } from "react";
import { api, fmtHour, type Mode } from "../api";
import { Assumptions, Btn, Card } from "../components";
import { useApp } from "../store";
import { MODES } from "./Family";
import { Markdown } from "../Chat";

const label = (m: string) => MODES.find((x) => x[0] === m)?.[1] ?? m;

function TripCompare() {
  const { t } = useApp();
  const [km, setKm] = useState(10);
  const [people, setPeople] = useState(1);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => { setBusy(true); try { setRes(await api.mobility(km, people)); } finally { setBusy(false); } };
  const max = res ? Math.max(...res.rows.map((r: any) => r.kg_co2_per_person), 0.001) : 1;
  return (
    <Card title="Green Mobility" icon="🚦" span={6}>
      <div className="row">
        <label className="field" style={{ flex: 1 }}>{t("trip_km")}<input type="number" min={1} max={500} value={km} onChange={(e) => setKm(+e.target.value || 1)} /></label>
        <label className="field" style={{ flex: 1 }}>{t("people")}<input type="number" min={1} max={8} value={people} onChange={(e) => setPeople(+e.target.value || 1)} /></label>
        <Btn busy={busy} onClick={run} style={{ alignSelf: "end" }}>{t("compare")}</Btn>
      </div>
      {res && (
        <div style={{ marginTop: 12 }} aria-live="polite">
          {res.rows.map((r: any, i: number) => (
            <div className="trip-row" key={r.mode} title={r.basis}>
              <span>{label(r.mode)}</span>
              <div className="meter" style={{ height: 12 }}>
                <span className="bar" style={{ display: "block", width: `${Math.max(2, (r.kg_co2_per_person / max) * 100)}%`, animationDelay: `${i * 50}ms` }} />
              </div>
              <b className="small">{r.kg_co2_per_person.toFixed(2)}</b>
            </div>
          ))}
          <p className="small muted">{t("kg_co2")}. ⚠️ {res.exposure_note}</p>
          <Assumptions items={res.rows.map((r: any) => `${label(r.mode)}: ${r.basis}`)} />
        </div>
      )}
    </Card>
  );
}

function WhatIf() {
  const { t, lang, place, ai } = useApp();
  const [from, setFrom] = useState<Mode>("car_petrol");
  const [to, setTo] = useState<Mode>("metro");
  const [km, setKm] = useState(8);
  const [days, setDays] = useState(5);
  const [hour, setHour] = useState(7);
  const [waste, setWaste] = useState(0);
  const [kwh, setKwh] = useState(0);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async (explain: boolean) => {
    setBusy(true); setErr(null);
    try {
      setRes(await api.whatIf({
        lat: place?.lat, lon: place?.lon, lang, explain,
        mode_shift: { from_mode: from, to_mode: to, distance_km_one_way: km, days_per_week: days },
        exercise_shift: place ? { current_hour: hour, duration_min: 45, intensity: "moderate" } : undefined,
        waste_burning: waste > 0 ? { kg_per_week: waste } : undefined,
        energy_saving: kwh > 0 ? { kwh_per_month: kwh } : undefined,
      }));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const r = res?.results;
  return (
    <Card title={t("whatif")} icon="🔮" span={6}>
      <div className="stack">
        <div className="row">
          <label className="field" style={{ flex: 1 }}>{t("from")}<select value={from} onChange={(e) => setFrom(e.target.value as Mode)}>{MODES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label className="field" style={{ flex: 1 }}>{t("to")}<select value={to} onChange={(e) => setTo(e.target.value as Mode)}>{MODES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        </div>
        <div className="row">
          <label className="field" style={{ flex: 1 }}>{t("km_one_way")}<input type="number" min={1} max={200} value={km} onChange={(e) => setKm(+e.target.value || 1)} /></label>
          <label className="field" style={{ flex: 1 }}>{t("days_week")} ({days})<input type="range" min={1} max={7} value={days} onChange={(e) => setDays(+e.target.value)} /></label>
        </div>
        <div className="row">
          <label className="field" style={{ flex: 1 }}>{t("exercise_at")}<select value={hour} onChange={(e) => setHour(+e.target.value)} disabled={!place}>
            {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{fmtHour(`0000-00-00T${String(h).padStart(2, "0")}`)}</option>)}</select></label>
          <label className="field" style={{ flex: 1 }}>🔥 kg waste/leaves burned per week<input type="number" min={0} max={200} value={waste} onChange={(e) => setWaste(+e.target.value || 0)} /></label>
        </div>
        <label className="field">⚡ kWh electricity saved per month<input type="number" min={0} max={2000} value={kwh} onChange={(e) => setKwh(+e.target.value || 0)} /></label>
        <div className="row">
          <Btn busy={busy} onClick={() => run(false)}>{t("run_whatif")}</Btn>
          {ai && <button className="btn ghost" disabled={busy} onClick={() => run(true)}>✨ {t("explain_ai")}</button>}
        </div>
        {err && <div className="notice warn" role="alert">{err}</div>}
        {r && (
          <div className="stack" aria-live="polite">
            <div className="row">
              <div className="stat" style={{ flex: 1 }}><b>{r.mode_shift.kg_co2_saved_year}</b><span className="small muted">kg CO₂ / year</span></div>
              {r.exercise_shift?.available && <div className="stat" style={{ flex: 1 }}><b>−{r.exercise_shift.dose_reduction_pct}%</b>
                <span className="small muted">PM2.5 inhaled if you exercise at {fmtHour(r.exercise_shift.best.time)}</span></div>}
              {r.waste_burning && <div className="stat" style={{ flex: 1 }}><b>{r.waste_burning.pm25_g_avoided_year} g</b><span className="small muted">PM2.5 smoke / year</span></div>}
              {r.energy_saving && <div className="stat" style={{ flex: 1 }}><b>{r.energy_saving.kg_co2_saved_year}</b><span className="small muted">kg CO₂ / year (power)</span></div>}
            </div>
            {res.explanation && <div className="notice ok" style={{ display: "block" }}>✨ <Markdown text={res.explanation} /></div>}
            <Assumptions items={[...r.mode_shift.assumptions, ...(r.exercise_shift?.assumptions ?? []),
              ...(r.waste_burning?.assumptions ?? []), ...(r.energy_saving?.assumptions ?? [])]} />
            <p className="small muted" style={{ margin: 0 }}>{res.disclaimer}</p>
          </div>
        )}
      </div>
    </Card>
  );
}

const QUICK = [
  { label: "🚇 Metro/bus instead of car (10 km)", kg: +(10 * (2.31 / 15 - 0.03)).toFixed(2) },
  { label: "🚲 Cycled/walked a 3 km errand", kg: +(3 * 2.31 / 45).toFixed(2) },
  { label: "🤝 Carpooled (3 people, 15 km)", kg: +(15 * 2.31 / 15 * (2 / 3)).toFixed(2) },
  { label: "🚦 Switched off engine at signals", kg: 0.1 },
  { label: "🍂 Composted leaves instead of burning", kg: 0 },
  { label: "💡 Saved 2 kWh electricity", kg: +(2 * 0.72).toFixed(2) },
];
const CHALLENGES = [
  { id: "car-free", title: "🚇 3 car-free commutes", need: 3, match: (l: string) => /Metro|Cycled|Carpool/.test(l) },
  { id: "no-burn", title: "🍂 Zero burning week", need: 1, match: (l: string) => l.includes("Composted") },
  { id: "idle", title: "🚦 5 idle-free signals", need: 5, match: (l: string) => l.includes("engine") },
];

function Tracker() {
  const { t, logs, addLog, removeLog } = useApp();
  const stats = useMemo(() => {
    const today = new Date();
    const days = Array.from({ length: 7 }, (_, i) => {
      const d = new Date(today); d.setDate(today.getDate() - (6 - i));
      const key = d.toISOString().slice(0, 10);
      return { key, day: d.toLocaleDateString(undefined, { weekday: "narrow" }), kg: logs.filter((l) => l.date === key).reduce((s, l) => s + l.kg, 0) };
    });
    const weekLogs = logs.filter((l) => l.date >= days[0].key);
    let streak = 0;
    for (let i = 6; i >= 0 && logs.some((l) => l.date === days[i].key); i--) streak++;
    return { days, week: weekLogs.reduce((s, l) => s + l.kg, 0), weekLogs, streak };
  }, [logs]);
  const max = Math.max(0.5, ...stats.days.map((d) => d.kg));

  return (
    <>
      <Card title={t("tracker")} icon="🌱" span={7}>
        <div className="row">
          <div className="stat" style={{ flex: 1 }}><b>{stats.week.toFixed(1)}</b><span className="small muted">{t("saved")} · {t("this_week")}</span></div>
          <div className="stat" style={{ flex: 1 }}><b>{stats.streak}🔥</b><span className="small muted">{t("streak")}</span></div>
          <div className="stat" style={{ flex: 1 }}><b>{stats.weekLogs.length}</b><span className="small muted">actions</span></div>
        </div>
        <div className="week" style={{ marginTop: 14 }} role="img" aria-label="CO2 saved per day this week">
          {stats.days.map((d, i) => <div key={d.key}><span style={{ height: `${(d.kg / max) * 60}px`, animationDelay: `${i * 60}ms` }} />{d.day}</div>)}
        </div>
        <div className="chips" style={{ marginTop: 14 }}>
          {QUICK.map((q) => <button key={q.label} className="chip" onClick={() => addLog({ label: q.label, kg: q.kg })}>＋ {q.label}</button>)}
        </div>
        {logs.length > 0 && (
          <ul className="small" style={{ paddingLeft: 0, listStyle: "none", maxHeight: 170, overflowY: "auto" }}>
            {logs.slice(0, 12).map((l) => (
              <li key={l.id} className="row" style={{ justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid var(--border)" }}>
                <span>{l.date} · {l.label}</span>
                <span className="row"><b>{l.kg} kg</b><button className="chip" aria-label={`Remove ${l.label}`} onClick={() => removeLog(l.id)}>✕</button></span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title={t("challenges")} icon="🏆" span={5}>
        <div className="stack">
          {CHALLENGES.map((c) => {
            const n = stats.weekLogs.filter((l) => c.match(l.label)).length;
            const done = n >= c.need;
            return (
              <div key={c.id} className="member">
                <div className="row" style={{ justifyContent: "space-between" }}><b>{c.title}</b><span>{done ? "🏅" : `${Math.min(n, c.need)}/${c.need}`}</span></div>
                <div className="meter" style={{ marginTop: 8 }}><span style={{ width: `${Math.min(1, n / c.need) * 100}%`, background: "linear-gradient(90deg,var(--accent),var(--brand2))" }} /></div>
              </div>
            );
          })}
          <p className="small muted" style={{ margin: 0 }}>Saved on this device only.</p>
        </div>
      </Card>
    </>
  );
}

export default function Impact() {
  const { t } = useApp();
  return (
    <div className="page">
      <div className="page-head"><h2>{t("impact_title")}</h2><p>{t("impact_sub")}</p></div>
      <div className="grid">
        <TripCompare />
        <WhatIf />
        <Tracker />
      </div>
    </div>
  );
}
