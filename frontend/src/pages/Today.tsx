import { useEffect, useState } from "react";
import { api, fmtHour, LEVEL_COLORS } from "../api";
import { AqiRing, aqiLabel, Btn, Card, CitySearch, ForecastBars, NumInput } from "../components";
import { AQI_HEALTH_HI } from "../i18n";
import { useApp } from "../store";

function localInput(offsetHours: number) {
  const d = new Date(Date.now() + offsetHours * 3600_000);
  d.setMinutes(0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
}

/** Android Chrome forbids `new Notification()`; use the service worker when there is one. Never let this break the check. */
function notify(body: string) {
  try {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    const opts = { body, icon: "/logo.svg" };
    if ("serviceWorker" in navigator && navigator.serviceWorker.controller) {
      navigator.serviceWorker.ready.then((r) => r.showNotification("BreatheWise", opts)).catch(() => {});
    } else {
      new Notification("BreatheWise", opts);
    }
  } catch { /* notifications are a bonus; the on-page alert already shows the message */ }
}

function Guardian() {
  const { t, tx, place, household } = useApp();
  const [title, setTitle] = useState(() => tx("Evening walk", "शाम की सैर"));
  const [start, setStart] = useState(() => localInput(3));
  const [mins, setMins] = useState(45);
  const [sensitive, setSensitive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    if (!place) return;
    setBusy(true); setErr(null);
    try {
      const r = await api.alerts(place, [{ title, start, duration_min: mins, sensitive }], household);
      setRes(r.alerts);
      const a = r.alerts[0];
      if (a?.status === "warn") notify(a.message);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <Card title={t("guardian")} icon="🛡️" span={5}>
      <p className="small muted" style={{ marginTop: -6 }}>{t("guardian_sub")}</p>
      <div className="stack">
        <label className="field">{t("activity")}<input type="text" value={title} maxLength={60} onChange={(e) => setTitle(e.target.value)} /></label>
        <div className="row">
          <label className="field" style={{ flex: 2 }}>{t("when")}<input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} /></label>
          <label className="field" style={{ flex: 1 }}>{t("minutes")}<NumInput min={5} max={720} value={mins} onChange={setMins} /></label>
        </div>
        <label className="check"><input type="checkbox" checked={sensitive} onChange={(e) => setSensitive(e.target.checked)} />{t("sensitive")}</label>
        <div className="row">
          <Btn busy={busy} onClick={run} disabled={!title.trim()}>{t("check")}</Btn>
          {"Notification" in window && Notification.permission === "default" && (
            <button className="btn ghost small" onClick={() => Notification.requestPermission()}>🔔 {t("alerts_btn")}</button>
          )}
        </div>
        {err && <div className="notice warn" role="alert">{err}</div>}
        {res?.map((a, i) => (
          <div key={i} className={`notice ${a.status === "warn" ? "warn" : a.status === "ok" ? "ok" : "info"}`} role="status">
            <span aria-hidden="true">{a.status === "warn" ? "⚠️" : a.status === "ok" ? "✅" : "ℹ️"}</span>
            <span>{a.message}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function AreaGrid() {
  const { t, tx, place } = useApp();
  const [cells, setCells] = useState<any[] | null>(null);
  useEffect(() => {
    if (!place) return;
    setCells(null);
    let stale = false; // a slow response for the previous city must not overwrite this one
    api.grid(place).then((g) => { if (!stale) setCells(g.cells); }).catch(() => { if (!stale) setCells([]); });
    return () => { stale = true; };
  }, [place]);
  return (
    <Card title={t("area")} icon="🗺️" span={7}>
      {!cells ? <div className="skeleton" style={{ height: 200 }} /> : cells.length === 0 ? <p className="muted">—</p> : (
        <>
          <div className="heat" role="img" aria-label="PM2.5 around you on a 5 by 5 model grid">
            <span className="sr-only">{tx("North is up.", "ऊपर उत्तर दिशा है।")}</span>
            {[...cells].reverse().reduce<any[][]>((rows, c, i) => { (rows[Math.floor(i / 5)] ||= []).unshift(c); return rows; }, [])
              .flat().map((c, i) => (
                <div key={i} className={i === 12 ? "me" : ""} style={{ background: c.color, animationDelay: `${i * 30}ms` }}
                  title={`PM2.5 ${c.pm2_5 ?? "?"} µg/m³`}>{c.pm2_5 != null ? Math.round(c.pm2_5) : "?"}</div>
              ))}
          </div>
          <p className="small muted">{t("area_note")}</p>
        </>
      )}
    </Card>
  );
}

export default function Today() {
  const { t, lang, place, setPlace, snap, loading, error, offlineSince, refresh } = useApp();
  // Label an hour with "tomorrow" when it falls on a later date than the current reading.
  const when = (iso: string) => `${fmtHour(iso)}${snap && iso.slice(0, 10) !== snap.observed_at.slice(0, 10) ? ` (${t("tomorrow")})` : ""}`;

  useEffect(() => {
    if (snap?.aqi.color) document.documentElement.style.setProperty("--aqi", snap.aqi.color);
  }, [snap]);

  if (!place) {
    return (
      <div className="page">
        <div className="card empty" style={{ marginTop: 18 }}>
          <div className="leaf" aria-hidden="true">🌬️</div>
          <h2 style={{ margin: "6px 0" }}>{t("hero_title")}</h2>
          <p className="muted">{t("hero_sub")}</p>
          <div style={{ maxWidth: 520, margin: "18px auto 0", textAlign: "left" }}><CitySearch onPick={setPlace} /></div>
          <div className="chips" style={{ justifyContent: "center", marginTop: 14 }}>
            {[["Delhi", 28.61, 77.21], ["Jabalpur", 23.17, 79.95], ["Lucknow", 26.85, 80.95], ["Mumbai", 19.08, 72.88]].map(([n, la, lo]) => (
              <button key={n as string} className="chip" onClick={() => setPlace({ name: n as string, lat: la as number, lon: lo as number })}>{n}</button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const today = snap?.windows[0];
  return (
    <div className="page">
      <div style={{ margin: "14px 0" }}><CitySearch onPick={setPlace} /></div>
      {offlineSince && <div className="notice info" role="status" style={{ marginBottom: 12 }}>📴 {t("offline")} {new Date(offlineSince).toLocaleString()}</div>}
      {error && !snap && (
        <div className="notice warn" role="alert">{error} <button className="btn small" onClick={refresh}>{t("retry")}</button></div>
      )}
      {loading && !snap && <div className="card"><div className="skeleton" style={{ height: 190 }} /><p className="center muted">{t("loading")}</p></div>}
      {snap && (
        <div className="grid">
          <section className="card span-12 hero" aria-live="polite">
            <AqiRing value={snap.aqi.value} label={snap.aqi.label} />
            <div style={{ position: "relative" }}>
              <div className="row">
                <span className="badge">{aqiLabel(snap.aqi.label, lang)}</span>
                <span className="tag" title={t("estimate_note")}>📡 {t("estimated")}</span>
              </div>
              <h2>📍 {place.name}</h2>
              <p style={{ margin: "4px 0 10px" }}>{lang === "hi" && snap.aqi.category ? AQI_HEALTH_HI[snap.aqi.category] ?? snap.aqi.health : snap.aqi.health}</p>
              <div className="small muted">
                {t("dominant")}: <b>{snap.aqi.dominant ?? "—"}</b> · US AQI {snap.aqi.us_aqi ?? "—"} · {t("updated")} {fmtHour(snap.observed_at)}
                {" "}({snap.location.timezone})
              </div>
            </div>
          </section>

          <Card title={t("next_hours")} icon="⏱️" span={7}>
            <ForecastBars hours={snap.hourly} nowIndex={snap.now_index} />
            {today && (
              <div className="windows" style={{ marginTop: 14 }}>
                <div className="win">
                  <div className="small muted">🌤️ {t("best_time")}</div>
                  <div className="t">{when(today.best.start)}</div>
                  <div className="small"><span className="dot" style={{ background: LEVEL_COLORS[today.best.level] }} /> PM2.5 ≈ {today.best.pm2_5}</div>
                </div>
                <div className="win">
                  <div className="small muted">🌫️ {t("worst_time")}</div>
                  <div className="t">{when(today.worst.start)}</div>
                  <div className="small"><span className="dot" style={{ background: LEVEL_COLORS[today.worst.level] }} /> PM2.5 ≈ {today.worst.pm2_5}</div>
                </div>
              </div>
            )}
          </Card>

          <Card title={t("pollutants")} icon="🧪" span={5}>
            <div className="pollutants">
              {Object.entries(snap.pollutants_now).map(([k, v]) => (
                <div key={k}><span className="small muted">{k}</span><b>{v == null ? "—" : k === "CO" ? v.toFixed(2) : Math.round(v)}</b>
                  <span className="small muted">{k === "CO" ? "mg/m³" : "µg/m³"}</span></div>
              ))}
            </div>
            {snap.smog_drivers.length > 0 && (
              <>
                <h3 style={{ marginTop: 16 }}><span aria-hidden="true">🌡️</span>{t("why_smog")}</h3>
                <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>{snap.smog_drivers.map((d) => <li key={d.key}>{d.text}</li>)}</ul>
              </>
            )}
          </Card>

          <Guardian />
          <AreaGrid />
        </div>
      )}
    </div>
  );
}
