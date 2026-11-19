import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { Btn, Card, NeedPlace } from "../components";
import { useApp } from "../store";

const CATS: [string, string][] = [
  ["waste_burning", "🔥 Garbage burning"], ["crop_burning", "🌾 Crop/leaf burning"], ["construction_dust", "🏗️ Construction dust"],
  ["industrial_smoke", "🏭 Factory smoke"], ["vehicle_smoke", "💨 Smoky vehicle"], ["traffic_jam", "🚗 Traffic jam"], ["other", "❓ Other"],
];
const catLabel = (c: string) => CATS.find((x) => x[0] === c)?.[1] ?? c;

export default function Community() {
  const { t, lang, place, ai } = useApp();
  const [reports, setReports] = useState<any[]>([]);
  const [cat, setCat] = useState("waste_burning");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiNote, setAiNote] = useState<string | null>(null);
  const [aiUsed, setAiUsed] = useState(false);
  const [msg, setMsg] = useState<{ kind: string; text: string } | null>(null);
  const [confirmed, setConfirmed] = useState<number[]>([]);

  const load = useCallback(() => { if (place) api.reports(place).then((r) => setReports(r.reports)).catch(() => {}); }, [place]);
  useEffect(load, [load]);

  const head = <div className="page-head"><h2>{t("community_title")}</h2><p>{t("community_sub")}</p></div>;
  if (!place) return <div className="page">{head}<NeedPlace /></div>;

  const onPhoto = async (file?: File) => {
    if (!file) return;
    setAiBusy(true); setAiNote(null);
    try {
      const r = await api.analyzePhoto(file, lang);
      if (r.category === "not_pollution") {
        setAiNote("AI could not see a pollution source in this photo.");
      } else {
        setCat(r.category); setDesc(r.suggested_description); setAiUsed(true);
        setAiNote(`AI saw: ${r.visible_signs.join(", ")} · severity ${r.severity} · confidence ${r.confidence}. ${r.note}`);
      }
    } catch (e) { setAiNote((e as Error).message); } finally { setAiBusy(false); }
  };

  const submit = async () => {
    setBusy(true); setMsg(null);
    try {
      await api.addReport({ category: cat, description: desc, lat: place.lat, lon: place.lon, ai_assisted: aiUsed });
      setDesc(""); setAiUsed(false); setAiNote(null);
      setMsg({ kind: "ok", text: "✅ Thanks! Your report is live for neighbours to confirm." });
      load();
    } catch (e) { setMsg({ kind: "warn", text: (e as Error).message }); } finally { setBusy(false); }
  };

  const confirm = async (id: number) => {
    const r = await api.confirmReport(id);
    setConfirmed((c) => [...c, id]);
    setReports((rs) => rs.map((x) => (x.id === id ? r : x)));
  };

  return (
    <div className="page">
      {head}
      <div className="grid">
        <Card span={5} title="📣">
          <div className="stack">
            <div className="field">{t("category")}
              <div className="chips">{CATS.map(([k, v]) => <button key={k} className="chip" aria-pressed={cat === k} onClick={() => setCat(k)}>{v}</button>)}</div>
            </div>
            <label className="field">{t("description")}
              <textarea rows={3} maxLength={500} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="e.g. Pile of garbage burning behind the market since morning" /></label>
            <label className="field">📷 {t("photo")}{!ai && " — AI key not set"}
              <input type="file" accept="image/jpeg,image/png,image/webp" disabled={aiBusy || !ai} onChange={(e) => onPhoto(e.target.files?.[0])} /></label>
            {aiBusy && <div className="skeleton" />}
            {aiNote && <div className="notice info">{aiNote}</div>}
            <Btn busy={busy} onClick={submit} disabled={desc.trim().length < 5}>{t("submit_report")}</Btn>
            {msg && <div className={`notice ${msg.kind}`} role="status">{msg.text}</div>}
            <p className="small muted" style={{ margin: 0 }}>🔒 {t("privacy_note")}</p>
          </div>
        </Card>
        <Card span={7} title={`${t("nearby")} (${reports.length})`} icon="📍">
          {reports.length === 0 ? <div className="empty"><div className="leaf" aria-hidden="true">🌳</div><p className="muted">{t("no_reports")}</p></div> : (
            <div className="stack">
              {reports.map((r, i) => (
                <div key={r.id} className="member" style={{ animation: `rise-in .4s ${i * 50}ms both` }}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <b>{catLabel(r.category)}</b>
                    <span className={`tag`}>{r.status === "confirmed" ? "✅ confirmed" : "⏳ unverified"}{r.ai_assisted ? " · AI" : ""}</span>
                  </div>
                  <p style={{ margin: "6px 0" }}>{r.description}</p>
                  <div className="row small muted" style={{ justifyContent: "space-between" }}>
                    <span>{new Date(r.created_at * 1000).toLocaleString()} · 👍 {r.confirmations}</span>
                    <button className="btn ghost small" disabled={confirmed.includes(r.id)} onClick={() => confirm(r.id)}>{t("confirm")}</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
