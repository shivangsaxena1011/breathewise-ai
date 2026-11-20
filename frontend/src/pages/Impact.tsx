import { useMemo, useState } from "react";
import { api, fmtHour, type Mode, type TripComparison, type WhatIfResponse } from "../api";
import { Assumptions, Btn, Card, NumInput } from "../components";
import { CHALLENGES, challengeProgress, logLabel, QUICK, weekStats } from "../eco";
import { useApp } from "../store";
import { MODES, modeLabel } from "./Family";
import { Markdown } from "../Chat";

/** Compare CO₂ per person for one trip across every travel mode. */
function TripCompare() {
  const { t, tx, lang } = useApp();
  const label = (m: string) => modeLabel(m, lang);
  const [km, setKm] = useState(10);
  const [people, setPeople] = useState(1);
  const [res, setRes] = useState<TripComparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    setBusy(true); setErr(null);
    try { setRes(await api.mobility(km, people)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const max = res ? Math.max(...res.rows.map((r) => r.kg_co2_per_person), 0.001) : 1;
  return (
    <Card title={tx("Green Mobility", "ग्रीन मोबिलिटी")} icon="🚦" span={6}>
      <div className="row">
        <label className="field" htmlFor="trip-km" style={{ flex: 1 }}>
          {t("trip_km")}
          <NumInput id="trip-km" min={1} max={500} value={km} onChange={setKm} />
        </label>
        <label className="field" htmlFor="trip-people" style={{ flex: 1 }}>
          {t("people")}
          <NumInput id="trip-people" min={1} max={8} value={people} onChange={setPeople} />
        </label>
        <Btn busy={busy} onClick={run} style={{ alignSelf: "end" }}>{t("compare")}</Btn>
      </div>
      {err && <div className="notice warn" role="alert" style={{ marginTop: 10 }}>{err}</div>}
      {res && (
        <div style={{ marginTop: 12 }} aria-live="polite">
          {res.rows.map((r, i) => (
            <div className="trip-row" key={r.mode} title={r.basis}>
              <span>{label(r.mode)}</span>
              <div className="meter" style={{ height: 12 }} aria-hidden="true">
                <span className="bar"
                  style={{ display: "block", width: `${Math.max(2, (r.kg_co2_per_person / max) * 100)}%`, animationDelay: `${i * 50}ms` }} />
              </div>
              <b className="small">{r.kg_co2_per_person.toFixed(2)}</b>
            </div>
          ))}
          <p className="small muted">{t("kg_co2")}. <span aria-hidden="true">⚠️</span> {res.exposure_note}</p>
          <Assumptions items={res.rows.map((r) => `${label(r.mode)}: ${r.basis}`)} />
        </div>
      )}
    </Card>
  );
}

/** What-If simulator: CO₂ from a mode shift, exposure from moving exercise, smoke from not burning waste. */
function WhatIf() {
  const { t, tx, lang, place, ai } = useApp();
  const [from, setFrom] = useState<Mode>("car_petrol");
  const [to, setTo] = useState<Mode>("metro");
  const [km, setKm] = useState(8);
  const [days, setDays] = useState(5);
  const [hour, setHour] = useState(7);
  const [waste, setWaste] = useState(0);
  const [kwh, setKwh] = useState(0);
  const [res, setRes] = useState<WhatIfResponse | null>(null);
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
  const ex = r?.exercise_shift?.available ? r.exercise_shift : null;
  const modeOptions = MODES.map(([k]) => <option key={k} value={k}>{modeLabel(k, lang)}</option>);
  return (
    <Card title={t("whatif")} icon="🔮" span={6}>
      <div className="stack">
        <div className="row">
          <label className="field" htmlFor="whatif-from" style={{ flex: 1 }}>{t("from")}
            <select id="whatif-from" value={from} onChange={(e) => setFrom(e.target.value as Mode)}>{modeOptions}</select></label>
          <label className="field" htmlFor="whatif-to" style={{ flex: 1 }}>{t("to")}
            <select id="whatif-to" value={to} onChange={(e) => setTo(e.target.value as Mode)}>{modeOptions}</select></label>
        </div>
        <div className="row">
          <label className="field" htmlFor="whatif-km" style={{ flex: 1 }}>{t("km_one_way")}
            <NumInput id="whatif-km" min={1} max={200} value={km} onChange={setKm} /></label>
          <label className="field" htmlFor="whatif-days" style={{ flex: 1 }}>{t("days_week")} ({days})
            <input id="whatif-days" type="range" min={1} max={7} value={days} onChange={(e) => setDays(+e.target.value)} /></label>
        </div>
        <div className="row">
          <label className="field" htmlFor="whatif-hour" style={{ flex: 1 }}>{t("exercise_at")}
            <select id="whatif-hour" value={hour} onChange={(e) => setHour(+e.target.value)} disabled={!place}>
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>{fmtHour(`0000-00-00T${String(h).padStart(2, "0")}`)}</option>
              ))}
            </select></label>
          <label className="field" htmlFor="whatif-waste" style={{ flex: 1 }}>
            <span><span aria-hidden="true">🔥</span> {tx("kg waste/leaves burned per week", "हर सप्ताह जलाया कचरा/पत्ते (किग्रा)")}</span>
            <NumInput id="whatif-waste" min={0} max={200} value={waste} onChange={setWaste} /></label>
        </div>
        <label className="field" htmlFor="whatif-kwh">
          <span><span aria-hidden="true">⚡</span> {tx("kWh electricity saved per month", "हर महीने बचाई बिजली (kWh)")}</span>
          <NumInput id="whatif-kwh" min={0} max={2000} value={kwh} onChange={setKwh} /></label>
        <div className="row">
          <Btn busy={busy} onClick={() => run(false)}>{t("run_whatif")}</Btn>
          {ai && (
            <button type="button" className="btn ghost" disabled={busy} onClick={() => run(true)}>
              <span aria-hidden="true">✨</span> {t("explain_ai")}
            </button>
          )}
        </div>
        {err && <div className="notice warn" role="alert">{err}</div>}
        {res && r && (
          <div className="stack" aria-live="polite">
            <div className="row">
              {r.mode_shift && <Stat value={r.mode_shift.kg_co2_saved_year} label={tx("kg CO₂ / year", "किग्रा CO₂ / वर्ष")} />}
              {ex && (ex.dose_reduction_pct > 0
                ? <Stat value={`−${ex.dose_reduction_pct}%`} label={`${t("dose_if_at")} ${fmtHour(ex.best.time)}`} />
                : <Stat value="✓" label={t("already_cleanest")} />)}
              {r.waste_burning && <Stat value={`${r.waste_burning.pm25_g_avoided_year} g`} label={tx("PM2.5 smoke / year", "PM2.5 धुआँ / वर्ष")} />}
              {r.energy_saving && <Stat value={r.energy_saving.kg_co2_saved_year} label={tx("kg CO₂ / year (power)", "किग्रा CO₂ / वर्ष (बिजली)")} />}
            </div>
            {res.explanation && (
              <div className="notice ok" style={{ display: "block" }}><span aria-hidden="true">✨</span> <Markdown text={res.explanation} /></div>
            )}
            <Assumptions items={[...(r.mode_shift?.assumptions ?? []), ...(ex?.assumptions ?? []),
              ...(r.waste_burning?.assumptions ?? []), ...(r.energy_saving?.assumptions ?? [])]} />
            <p className="small muted" style={{ margin: 0 }}>{res.disclaimer}</p>
          </div>
        )}
      </div>
    </Card>
  );
}

/** One headline number with a caption underneath. */
function Stat({ value, label }: { value: string | number; label: string }) {
  return <div className="stat" style={{ flex: 1 }}><b>{value}</b><span className="small muted">{label}</span></div>;
}

/** Eco tracker: log green actions on this device and follow weekly challenges. */
function Tracker() {
  const { t, tx, lang, logs, addLog, removeLog } = useApp();
  const stats = useMemo(() => weekStats(logs, new Date(), lang === "hi" ? "hi-IN" : "en-IN"), [logs, lang]);
  const max = Math.max(0.5, ...stats.days.map((d) => d.kg));

  return (
    <>
      <Card title={t("tracker")} icon="🌱" span={7}>
        <div className="row">
          <Stat value={stats.week.toFixed(1)} label={`${t("saved")} · ${t("this_week")}`} />
          <Stat value={`${stats.streak}🔥`} label={t("streak")} />
          <Stat value={stats.weekLogs.length} label={tx("actions", "कदम")} />
        </div>
        <div className="week" style={{ marginTop: 14 }} role="img" aria-label={tx("CO₂ saved per day this week", "इस सप्ताह रोज़ बचाया CO₂")}>
          {stats.days.map((d, i) => (
            <div key={d.key}><span style={{ height: `${(d.kg / max) * 60}px`, animationDelay: `${i * 60}ms` }} />{d.day}</div>
          ))}
        </div>
        <div className="chips" style={{ marginTop: 14 }}>
          {QUICK.map((q) => (
            <button key={q.kind} type="button" className="chip" onClick={() => addLog({ label: q.en, kind: q.kind, kg: q.kg })}>
              <span aria-hidden="true">＋</span> {lang === "hi" ? q.hi : q.en}
            </button>
          ))}
        </div>
        {logs.length > 0 && (
          <ul className="small" style={{ paddingLeft: 0, listStyle: "none", maxHeight: 170, overflowY: "auto" }}>
            {logs.slice(0, 12).map((l) => (
              <li key={l.id} className="row" style={{ justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid var(--border)" }}>
                <span>{l.date} · {logLabel(l, lang)}</span>
                <span className="row">
                  <b>{l.kg} kg</b>
                  <button type="button" className="chip" aria-label={`${t("remove")} ${logLabel(l, lang)}`} onClick={() => removeLog(l.id)}>✕</button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title={t("challenges")} icon="🏆" span={5}>
        <div className="stack">
          {CHALLENGES.map((c) => {
            const { count, done, ratio } = challengeProgress(c, stats.weekLogs);
            return (
              <div key={c.id} className="member">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <b>{lang === "hi" ? c.hi : c.en}</b>
                  <span>{done ? <span role="img" aria-label={tx("Done", "पूरा")}>🏅</span> : `${count}/${c.need}`}</span>
                </div>
                <div className="meter" style={{ marginTop: 8 }} aria-hidden="true">
                  <span style={{ width: `${ratio * 100}%`, background: "linear-gradient(90deg,var(--accent),var(--brand2))" }} />
                </div>
              </div>
            );
          })}
          <p className="small muted" style={{ margin: 0 }}>{tx("Saved on this device only.", "सिर्फ़ इसी डिवाइस पर सेव है।")}</p>
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
