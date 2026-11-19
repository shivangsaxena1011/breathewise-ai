import { useState } from "react";
import { api, fmtHour, type Home } from "../api";
import { ActionList, Btn, Card, NeedPlace } from "../components";
import { useApp } from "../store";

const ROOMS: [string, string][] = [["living", "🛋️ Living"], ["bedroom", "🛏️ Bedroom"], ["kitchen", "🍳 Kitchen"], ["kids", "🧸 Kids"], ["study", "📚 Study"], ["bathroom", "🚿 Bath"]];
const VERDICT = { open: ["🪟", "ok"], brief: ["⏱️", "info"], closed: ["🔒", "warn"] } as const;

export default function HomeAir() {
  const { t, lang, place, household, setHousehold } = useApp();
  const [rooms, setRooms] = useState<Record<string, number>>({ living: 16, bedroom: 12, kitchen: 8 });
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const home = household.home;
  const setHome = (h: Partial<Home>) => setHousehold({ ...household, home: { ...home, ...h } });

  const head = <div className="page-head"><h2>{t("home_title")}</h2><p>{t("home_sub")}</p></div>;
  if (!place) return <div className="page">{head}<NeedPlace /></div>;

  const run = async () => {
    setBusy(true); setErr(null);
    try {
      setRes(await api.indoor(place, home, Object.entries(rooms).map(([kind, area_m2]) => ({ kind, area_m2 })), lang));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  const toggleRoom = (k: string) => setRooms((r) => {
    const n = { ...r };
    if (k in n) delete n[k]; else n[k] = 12;
    return n;
  });

  return (
    <div className="page">
      {head}
      <div className="grid">
        <Card span={5} title={t("home_title")} icon="🏡">
          <div className="stack">
            <label className="check"><input type="checkbox" checked={home.has_purifier} onChange={(e) => setHome({ has_purifier: e.target.checked })} />{t("purifier")}</label>
            <label className="check"><input type="checkbox" checked={home.smoker_at_home} onChange={(e) => setHome({ smoker_at_home: e.target.checked })} />{t("smoker")}</label>
            <label className="check"><input type="checkbox" checked={home.burns_incense} onChange={(e) => setHome({ burns_incense: e.target.checked })} />{t("incense")}</label>
            <label className="check"><input type="checkbox" checked={home.has_pets} onChange={(e) => setHome({ has_pets: e.target.checked })} />{t("pets")}</label>
            <label className="field">{t("fuel")}
              <select value={home.cooking_fuel} onChange={(e) => setHome({ cooking_fuel: e.target.value as Home["cooking_fuel"] })}>
                <option value="lpg">LPG</option><option value="png">Piped gas (PNG)</option><option value="induction">Induction / electric</option>
                <option value="biomass">Wood / dung / coal</option><option value="kerosene">Kerosene</option>
              </select></label>
            <div className="field">{t("rooms")}
              <div className="chips">
                {ROOMS.map(([k, v]) => <button key={k} className="chip" aria-pressed={k in rooms} onClick={() => toggleRoom(k)}>{v}</button>)}
              </div>
            </div>
            {Object.keys(rooms).map((k) => (
              <label key={k} className="field">{ROOMS.find((r) => r[0] === k)?.[1]} — {rooms[k]} m²
                <input type="range" min={4} max={40} value={rooms[k]} onChange={(e) => setRooms({ ...rooms, [k]: +e.target.value })} />
              </label>
            ))}
            <Btn busy={busy} onClick={run} disabled={Object.keys(rooms).length === 0}>🩺 {t("check_home")}</Btn>
            {err && <div className="notice warn" role="alert">{err}</div>}
          </div>
        </Card>

        {!res ? (
          <div className="card span-7 empty"><div className="leaf" aria-hidden="true">🪴</div><p className="muted">{t("home_sub")}</p></div>
        ) : (
          <div className="span-7 stack" aria-live="polite">
            <section className="card">
              <h3>{VERDICT[res.ventilation.verdict as keyof typeof VERDICT][0]} {t("windows_now")}</h3>
              <div className={`notice ${VERDICT[res.ventilation.verdict as keyof typeof VERDICT][1]}`}>{res.ventilation.text}</div>
              {res.ventilation.best_window && (
                <p className="small muted">🌤️ {t("best_time")}: <b>{fmtHour(res.ventilation.best_window.start)}</b> (PM2.5 ≈ {res.ventilation.best_window.pm2_5})</p>
              )}
              <p className="small muted" style={{ marginBottom: 0 }}>{res.ventilation.why}</p>
            </section>
            {res.rooms.map((r: any, i: number) => (
              <section key={r.kind} className="card" style={{ animationDelay: `${i * 80}ms` }}>
                <h3>{ROOMS.find((x) => x[0] === r.kind)?.[1]}</h3>
                <ActionList items={r.tips.map((x: any) => ({ ...x, priority: "medium" }))} />
                <p className="small muted" style={{ marginBottom: 0 }}>💨 {t("purifier_need")}: <b>{r.purifier.cadr_m3h} m³/h</b> (~{r.purifier.cadr_cfm} CFM) · {r.purifier.basis}</p>
              </section>
            ))}
            <section className="card"><h3>✅</h3><ActionList items={res.general.map((x: any) => ({ ...x, priority: "low" }))} /></section>
          </div>
        )}
      </div>
    </div>
  );
}
