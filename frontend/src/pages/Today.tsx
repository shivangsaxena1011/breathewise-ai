import { useEffect, useState } from "react";
import {
  api, fmtHour, LEVEL_COLORS, levelInk, type ActivityAlert, type GridCell, type Place, type Snapshot, type Station,
} from "../api";
import { AqiRing, aqiLabel, Btn, Card, CitySearch, ForecastBars, NumInput } from "../components";
import { AQI_HEALTH_HI } from "../i18n";
import { useApp } from "../store";

/** 0 is clean air, not "missing": only null/undefined/NaN show a dash. */
export function usAqiText(v: number | null | undefined): string {
  return v == null || Number.isNaN(v) ? "—" : String(Math.round(v));
}

/** A start time a few hours ahead, in the selected city's own clock (forecast hours are city-local). */
export function cityTimeAhead(snap: Snapshot | null, hoursAhead: number): string {
  const h = snap?.hourly[Math.min((snap?.now_index ?? 0) + hoursAhead, (snap?.hourly.length ?? 1) - 1)];
  if (h) return h.time.slice(0, 16);
  const d = new Date(Date.now() + hoursAhead * 3600_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
}

/** Android Chrome forbids `new Notification()`; use the service worker when there is one. Never let this break the check. */
function notify(body: string) {
  try {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    const opts = { body, icon: "/logo-192.png" };
    if ("serviceWorker" in navigator && navigator.serviceWorker.controller) {
      navigator.serviceWorker.ready.then((r) => r.showNotification("BreatheWise", opts)).catch(() => {});
    } else {
      new Notification("BreatheWise", opts);
    }
  } catch { /* notifications are a bonus; the on-page alert already shows the message */ }
}

/** Hindi text for a smog driver, filled with the live weather numbers. */
function driverHi(key: string, snap: Snapshot): string | null {
  const w = snap.weather_now;
  if (key === "low_wind") return `हवा बहुत धीमी है (${Math.round(w.wind_speed_10m ?? 0)} किमी/घंटा) — प्रदूषण दूर नहीं जा रहा।`;
  if (key === "low_mixing") return `हवा की ऊपर-नीचे मिलने वाली परत बहुत नीची है (~${Math.round(w.boundary_layer_height ?? 0)} मीटर) — धुआँ और धूल ज़मीन के पास फँसे हैं।`;
  if (key === "fog") return "ठंडी, नम हवा — कोहरा धुएँ के साथ मिलकर घना स्मॉग बना सकता है।";
  return null;
}

/** Live monitoring-station reading. Attribution to the data sources is required by the station data terms. */
function StationLine({ st, timeZone }: { st: Station; timeZone: string }) {
  const { t } = useApp();
  // Show the city's own clock time, not the viewer's.
  let time = st.measured_at.slice(11, 16);
  try { time = new Date(st.measured_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZone }); } catch { /* unknown tz */ }
  return (
    <div className="station" role="note">
      <div>
        📍 {t("measured_at")} <b>{st.name}</b> · {st.distance_km} {t("km_away")} · {time} ({st.age_minutes} {t("min_ago")})
      </div>
      <div className="row" style={{ gap: 14, marginTop: 4 }}>
        <span>US AQI <b>{Math.round(st.us_aqi)}</b></span>
        {st.pm25 != null && <span>PM2.5 ≈ <b>{Math.round(st.pm25)}</b> µg/m³</span>}
        {st.calibration.pm2_5 != null && <span className="muted">{t("model_correction")}{st.calibration.pm2_5}</span>}
      </div>
      {st.attributions.length > 0 && (
        <div className="small muted" style={{ marginTop: 4 }}>
          {t("station_data")}:{" "}
          {st.attributions.map((a, i) => (
            <span key={a.name}>{i > 0 && " · "}{/^https?:\/\//.test(a.url)
              ? <a href={a.url} target="_blank" rel="noopener noreferrer">{a.name}</a> : a.name}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function Guardian() {
  const { t, tx, lang, place, household, snap } = useApp();
  const [title, setTitle] = useState(() => tx("Evening walk", "शाम की सैर"));
  // Until the user picks a time, the default follows the selected city's clock.
  const [picked, setPicked] = useState<string | null>(null);
  const start = picked ?? cityTimeAhead(snap, 3);
  const [mins, setMins] = useState(45);
  const [sensitive, setSensitive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<ActivityAlert[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    if (!place) return;
    setBusy(true); setErr(null);
    try {
      const r = await api.alerts(place, [{ title, start, duration_min: mins, sensitive }], household, lang);
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
          <label className="field" style={{ flex: 2 }}>{t("when")} {snap && <span className="muted">({snap.location.timezone})</span>}
            <input type="datetime-local" value={start} onChange={(e) => setPicked(e.target.value)} /></label>
          <label className="field" style={{ flex: 1 }}>{t("minutes")}<NumInput min={5} max={720} value={mins} onChange={setMins} /></label>
        </div>
        <label className="check"><input type="checkbox" checked={sensitive} onChange={(e) => setSensitive(e.target.checked)} />{t("sensitive")}</label>
        <div className="row">
          <Btn busy={busy} onClick={run} disabled={!title.trim()}>{t("check")}</Btn>
          {"Notification" in window && Notification.permission === "default" && (
            <button type="button" className="btn ghost small" onClick={() => Notification.requestPermission()}>
              <span aria-hidden="true">🔔</span> {t("alerts_btn")}
            </button>
          )}
        </div>
        {err && <div className="notice warn" role="alert">{err}</div>}
        <div aria-live="polite" className="stack">
          {res?.map((a) => (
            <div key={`${a.activity}-${a.start}`} className={`notice ${ALERT_STYLE[a.status][0]}`}>
              <span aria-hidden="true">{ALERT_STYLE[a.status][1]}</span>
              <span>{a.message}</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

const ALERT_STYLE: Record<ActivityAlert["status"], [string, string]> = {
  warn: ["warn", "⚠️"], ok: ["ok", "✅"], unknown: ["info", "ℹ️"],
};

/** The API lists the 5×5 grid south→north, west→east; draw rows north-first so north is up. */
export function northUp(cells: GridCell[], size = 5): GridCell[] {
  const rows: GridCell[][] = [];
  for (let i = 0; i < cells.length; i += size) rows.push(cells.slice(i, i + size));
  return rows.reverse().flat();
}

const gridKey = (p: Place) => `${p.lat},${p.lon}`;

function AreaGrid() {
  const { t, tx, place } = useApp();
  const [grid, setGrid] = useState<{ key: string; cells: GridCell[] } | null>(null);
  useEffect(() => {
    if (!place) return;
    const key = gridKey(place);
    let stale = false; // a slow response for the previous city must not overwrite this one
    api.grid(place)
      .then((g) => { if (!stale) setGrid({ key, cells: g.cells }); })
      .catch(() => { if (!stale) setGrid({ key, cells: [] }); });
    return () => { stale = true; };
  }, [place]);
  const cells = place && grid?.key === gridKey(place) ? grid.cells : null;
  return (
    <Card title={t("area")} icon="🗺️" span={7}>
      {!cells ? <div className="skeleton" role="status" aria-label={t("loading")} style={{ height: 200 }} />
        : cells.length === 0 ? <p className="muted">—</p> : (
          <>
            <div className="heat" role="img"
              aria-label={tx("PM2.5 around you on a 5 by 5 model grid. North is up; your location is in the centre.",
                "आपके आसपास PM2.5, 5×5 मॉडल ग्रिड पर। ऊपर उत्तर है; आपकी जगह बीच में है।")}>
              {northUp(cells).map((c, i) => (
                <div key={`${c.lat},${c.lon}`} className={i === 12 ? "me" : ""}
                  style={{ background: c.color, color: levelInk(c.level), animationDelay: `${i * 30}ms` }}
                  title={`PM2.5 ${c.pm2_5 ?? "?"} µg/m³`}>{c.pm2_5 != null ? Math.round(c.pm2_5) : "?"}</div>
              ))}
            </div>
            <p className="small muted">{t("area_note")}</p>
          </>
        )}
    </Card>
  );
}

const QUICK_CITIES: Place[] = [
  { name: "Delhi", lat: 28.61, lon: 77.21 }, { name: "Jabalpur", lat: 23.17, lon: 79.95 },
  { name: "Lucknow", lat: 26.85, lon: 80.95 }, { name: "Mumbai", lat: 19.08, lon: 72.88 },
];

export default function Today() {
  const { t, lang, place, setPlace, snap, loading, error, offlineSince, refresh } = useApp();
  // Label an hour with "tomorrow" when it falls on a later date than the current reading.
  const when = (iso: string) => `${fmtHour(iso)}${snap && iso.slice(0, 10) !== snap.observed_at.slice(0, 10) ? ` (${t("tomorrow")})` : ""}`;

  useEffect(() => {
    if (!snap?.aqi.color) return;
    const root = document.documentElement.style;
    root.setProperty("--aqi", snap.aqi.color);
    root.setProperty("--aqi-ink", levelInk(snap.aqi.level));
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
            {QUICK_CITIES.map((c) => (
              <button key={c.name} type="button" className="chip" onClick={() => setPlace(c)}>{c.name}</button>
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
      {offlineSince && (
        <div className="notice info" role="status" style={{ marginBottom: 12 }}>
          <span aria-hidden="true">📴</span> {t("offline")} {new Date(offlineSince).toLocaleString()}
        </div>
      )}
      {error && !snap && (
        <div className="notice warn" role="alert">
          {error} <button type="button" className="btn small" onClick={refresh}>{t("retry")}</button>
        </div>
      )}
      {loading && !snap && (
        <div className="card" aria-busy="true">
          <div className="skeleton" style={{ height: 190 }} />
          <p className="center muted" role="status">{t("loading")}</p>
        </div>
      )}
      {snap && (
        <div className="grid">
          <section className="card span-12 hero" aria-live="polite">
            <AqiRing value={snap.aqi.value} label={snap.aqi.label} />
            <div style={{ position: "relative" }}>
              <div className="row">
                <span className="badge">{aqiLabel(snap.aqi.label, lang)}</span>
                {snap.aqi.basis === "station_calibrated"
                  ? <span className="tag live" title={t("calibrated_note")}><span className="live-dot" aria-hidden="true" /> {t("calibrated")}</span>
                  : <span className="tag" title={t("estimate_note")}>📡 {t("estimated")}</span>}
              </div>
              <h2>📍 {place.name}</h2>
              <p style={{ margin: "4px 0 10px" }}>{lang === "hi" && snap.aqi.category ? AQI_HEALTH_HI[snap.aqi.category] ?? snap.aqi.health : snap.aqi.health}</p>
              <div className="small muted">
                {t("dominant")}: <b>{snap.aqi.dominant ?? "—"}</b> · US AQI {usAqiText(snap.station?.us_aqi ?? snap.aqi.us_aqi)} · {t("updated")} {fmtHour(snap.observed_at)}
                {" "}({snap.location.timezone})
              </div>
              {snap.station && <StationLine st={snap.station} timeZone={snap.location.timezone} />}
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
                <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>{snap.smog_drivers.map((d) => <li key={d.key}>{lang === "hi" ? driverHi(d.key, snap) ?? d.text : d.text}</li>)}</ul>
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
