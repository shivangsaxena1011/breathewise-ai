import { useId, useState } from "react";
import { api, fmtHour, type Home, type IndoorReport, type RoomKind, type Verdict } from "../api";
import { ActionList, Btn, Card, NeedPlace } from "../components";
import { useApp } from "../store";

const ROOMS: [RoomKind, string, string][] = [["living", "🛋️ Living", "🛋️ बैठक"], ["bedroom", "🛏️ Bedroom", "🛏️ शयनकक्ष"],
  ["kitchen", "🍳 Kitchen", "🍳 रसोई"], ["kids", "🧸 Kids", "🧸 बच्चों का कमरा"], ["study", "📚 Study", "📚 पढ़ाई"], ["bathroom", "🚿 Bath", "🚿 बाथरूम"]];
const VERDICT: Record<Verdict, [icon: string, tone: string]> = { open: ["🪟", "ok"], brief: ["⏱️", "info"], closed: ["🔒", "warn"] };
const DEFAULT_ROOMS: Partial<Record<RoomKind, number>> = { living: 16, bedroom: 12, kitchen: 8 };

type HomeFlag = "has_purifier" | "smoker_at_home" | "burns_incense" | "has_pets";
const HOME_CHECKS: [HomeFlag, "purifier" | "smoker" | "incense" | "pets"][] = [
  ["has_purifier", "purifier"], ["smoker_at_home", "smoker"], ["burns_incense", "incense"], ["has_pets", "pets"],
];

export default function HomeAir() {
  const { t, tx, lang, place, household, setHousehold } = useApp();
  const roomsId = useId();
  const roomLabel = (k: RoomKind) => {
    const r = ROOMS.find((x) => x[0] === k);
    return r ? (lang === "hi" ? r[2] : r[1]) : k;
  };
  const [rooms, setRooms] = useState<Partial<Record<RoomKind, number>>>(DEFAULT_ROOMS);
  const roomList = Object.entries(rooms) as [RoomKind, number][];
  const [res, setRes] = useState<IndoorReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const home = household.home;
  const setHome = (h: Partial<Home>) => setHousehold({ ...household, home: { ...home, ...h } });

  const head = <div className="page-head"><h2>{t("home_title")}</h2><p>{t("home_sub")}</p></div>;
  if (!place) return <div className="page">{head}<NeedPlace /></div>;

  const run = async () => {
    setBusy(true); setErr(null);
    try {
      setRes(await api.indoor(place, home, roomList.map(([kind, area_m2]) => ({ kind, area_m2 })), lang));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  const toggleRoom = (k: RoomKind) => setRooms((r) => {
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
            {HOME_CHECKS.map(([field, key]) => (
              <label key={field} className="check">
                <input type="checkbox" checked={home[field]} onChange={(e) => setHome({ [field]: e.target.checked })} />{t(key)}
              </label>
            ))}
            <label className="field">{t("fuel")}
              <select value={home.cooking_fuel} onChange={(e) => setHome({ cooking_fuel: e.target.value as Home["cooking_fuel"] })}>
                <option value="lpg">LPG</option>
                <option value="png">{tx("Piped gas (PNG)", "पाइप गैस (PNG)")}</option>
                <option value="induction">{tx("Induction / electric", "इंडक्शन / बिजली")}</option>
                <option value="biomass">{tx("Wood / dung / coal", "लकड़ी / उपले / कोयला")}</option>
                <option value="kerosene">{tx("Kerosene", "मिट्टी का तेल")}</option>
              </select></label>
            <div className="field">
              <span id={roomsId}>{t("rooms")}</span>
              <div className="chips" role="group" aria-labelledby={roomsId}>
                {ROOMS.map(([k]) => (
                  <button key={k} type="button" className="chip" aria-pressed={k in rooms} onClick={() => toggleRoom(k)}>{roomLabel(k)}</button>
                ))}
              </div>
            </div>
            {roomList.map(([k, area]) => (
              <label key={k} className="field">{roomLabel(k)} — {area} m²
                <input type="range" min={4} max={40} value={area} aria-valuetext={`${area} m²`}
                  onChange={(e) => setRooms({ ...rooms, [k]: +e.target.value })} />
              </label>
            ))}
            <Btn busy={busy} onClick={run} disabled={roomList.length === 0}><span aria-hidden="true">🩺</span> {t("check_home")}</Btn>
            {err && <div className="notice warn" role="alert">{err}</div>}
          </div>
        </Card>

        {!res ? (
          <div className="card span-7 empty">
            <div className="leaf" aria-hidden="true">🪴</div><p className="muted">{t("home_sub")}</p>
          </div>
        ) : (
          <div className="span-7 stack" aria-live="polite">
            <section className="card">
              <h3><span aria-hidden="true">{VERDICT[res.ventilation.verdict][0]}</span> {t("windows_now")}</h3>
              <div className={`notice ${VERDICT[res.ventilation.verdict][1]}`}>{res.ventilation.text}</div>
              {res.ventilation.best_window && (
                <p className="small muted">
                  <span aria-hidden="true">🌤️</span> {t("best_time")}: <b>{fmtHour(res.ventilation.best_window.start)}</b>
                  {" "}(PM2.5 ≈ {res.ventilation.best_window.pm2_5})
                </p>
              )}
              <p className="small muted" style={{ marginBottom: 0 }}>{res.ventilation.why}</p>
            </section>
            {res.rooms.map((r, i) => (
              <section key={r.kind} className="card" style={{ animationDelay: `${i * 80}ms` }}>
                <h3>{roomLabel(r.kind)}</h3>
                <ActionList items={r.tips.map((x) => ({ ...x, priority: "medium" }))} />
                <p className="small muted" style={{ marginBottom: 0 }}>
                  <span aria-hidden="true">💨</span> {t("purifier_need")}: <b>{r.purifier.cadr_m3h} m³/h</b>
                  {" "}(~{r.purifier.cadr_cfm} CFM) · {r.purifier.basis}
                </p>
              </section>
            ))}
            <section className="card">
              <h3><span aria-hidden="true">✅</span> {tx("For the whole home", "पूरे घर के लिए")}</h3>
              <ActionList items={res.general.map((x) => ({ ...x, priority: "low" }))} />
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
