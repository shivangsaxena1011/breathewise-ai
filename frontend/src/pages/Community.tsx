import { useCallback, useEffect, useId, useState } from "react";
import { api, type Report, type ReportCategory } from "../api";
import { Btn, Card, NeedPlace } from "../components";
import { useApp } from "../store";

const CATS: [ReportCategory, string, string][] = [
  ["waste_burning", "🔥 Garbage burning", "🔥 कचरा जलाना"], ["crop_burning", "🌾 Crop/leaf burning", "🌾 फसल/पत्ते जलाना"],
  ["construction_dust", "🏗️ Construction dust", "🏗️ निर्माण की धूल"], ["industrial_smoke", "🏭 Factory smoke", "🏭 फ़ैक्ट्री का धुआँ"],
  ["vehicle_smoke", "💨 Smoky vehicle", "💨 धुआँ छोड़ता वाहन"], ["traffic_jam", "🚗 Traffic jam", "🚗 ट्रैफ़िक जाम"], ["other", "❓ Other", "❓ अन्य"],
];

const MAX_PHOTO_BYTES = 4 * 1024 * 1024;

/** Strip links and markup so AI text always passes the report rules (≤500 chars, no links). */
export function cleanDescription(text: string): string {
  return text.replace(/https?:\/\/\S+|www\.\S+/gi, "").replace(/<[^>]*>/g, "").slice(0, 500).trim();
}

export default function Community() {
  const { t, tx, lang, place, ai } = useApp();
  const catId = useId();
  const catLabel = (c: ReportCategory) => {
    const r = CATS.find((x) => x[0] === c);
    return r ? (lang === "hi" ? r[2] : r[1]) : c;
  };
  const [reports, setReports] = useState<Report[]>([]);
  const [cat, setCat] = useState<ReportCategory>("waste_burning");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiNote, setAiNote] = useState<string | null>(null);
  const [aiUsed, setAiUsed] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "warn"; text: string } | null>(null);
  const [confirmed, setConfirmed] = useState<number[]>([]);

  const load = useCallback(() => {
    if (place) api.reports(place).then((r) => setReports(r.reports)).catch(() => { /* list stays as it was */ });
  }, [place]);
  useEffect(load, [load]);

  const head = <div className="page-head"><h2>{t("community_title")}</h2><p>{t("community_sub")}</p></div>;
  if (!place) return <div className="page">{head}<NeedPlace /></div>;

  const onPhoto = async (input: HTMLInputElement) => {
    const file = input.files?.[0];
    input.value = ""; // allow choosing the same photo again
    if (!file) return;
    if (file.size > MAX_PHOTO_BYTES) { setAiNote(t("photo_too_big")); return; }
    setAiBusy(true); setAiNote(null);
    try {
      const r = await api.analyzePhoto(file, lang);
      if (r.category === "not_pollution") {
        setAiNote(tx("AI could not see a pollution source in this photo.", "AI को इस फ़ोटो में प्रदूषण का स्रोत नहीं दिखा।"));
      } else {
        setCat(r.category);
        setDesc(cleanDescription(String(r.suggested_description ?? "")));
        setAiUsed(true);
        setAiNote(`${tx("AI saw", "AI ने देखा")}: ${r.visible_signs.join(", ")} · ${tx("severity", "गंभीरता")} ${r.severity}`
          + ` · ${tx("confidence", "भरोसा")} ${r.confidence}. ${r.note}`);
      }
    } catch (e) { setAiNote((e as Error).message); } finally { setAiBusy(false); }
  };

  const submit = async () => {
    setBusy(true); setMsg(null);
    try {
      await api.addReport({ category: cat, description: desc, lat: place.lat, lon: place.lon, ai_assisted: aiUsed });
      setDesc(""); setAiUsed(false); setAiNote(null);
      setMsg({
        kind: "ok",
        text: tx("✅ Thanks! Your report is live for neighbours to confirm.", "✅ धन्यवाद! आपकी रिपोर्ट पड़ोसियों की पुष्टि के लिए दिख रही है।"),
      });
      load();
    } catch (e) { setMsg({ kind: "warn", text: (e as Error).message }); } finally { setBusy(false); }
  };

  const confirm = async (id: number) => {
    setConfirmed((c) => [...c, id]); // disable at once so double-clicks don't double-count
    try {
      const r = await api.confirmReport(id);
      setReports((rs) => rs.map((x) => (x.id === id ? r : x)));
    } catch (e) {
      setConfirmed((c) => c.filter((x) => x !== id));
      setMsg({ kind: "warn", text: (e as Error).message });
    }
  };

  return (
    <div className="page">
      {head}
      <div className="grid">
        <Card span={5} icon="📣" title={tx("Report a pollution source", "प्रदूषण के स्रोत की रिपोर्ट करें")}>
          <div className="stack">
            <div className="field">
              <span id={catId}>{t("category")}</span>
              <div className="chips" role="group" aria-labelledby={catId}>
                {CATS.map(([k]) => (
                  <button key={k} type="button" className="chip" aria-pressed={cat === k} onClick={() => setCat(k)}>{catLabel(k)}</button>
                ))}
              </div>
            </div>
            <label className="field" htmlFor="report-description">{t("description")}
              <textarea id="report-description" rows={3} maxLength={500} value={desc} onChange={(e) => setDesc(e.target.value)}
                placeholder={tx("e.g. Pile of garbage burning behind the market since morning", "जैसे: सुबह से बाज़ार के पीछे कचरे का ढेर जल रहा है")} />
            </label>
            <label className="field" htmlFor="report-photo">
              <span><span aria-hidden="true">📷</span> {t("photo")}{!ai && tx(" — AI key not set", " — AI कुंजी सेट नहीं")}</span>
              <input id="report-photo" type="file" accept="image/jpeg,image/png,image/webp" disabled={aiBusy || !ai} onChange={(e) => onPhoto(e.currentTarget)} />
            </label>
            {aiBusy && <div className="skeleton" role="status" aria-label={t("busy")} />}
            {aiNote && <div className="notice info" role="status">{aiNote}</div>}
            <Btn busy={busy} onClick={submit} disabled={desc.trim().length < 5}>{t("submit_report")}</Btn>
            {msg && <div className={`notice ${msg.kind}`} role="status">{msg.text}</div>}
            <p className="small muted" style={{ margin: 0 }}><span aria-hidden="true">🔒</span> {t("privacy_note")}</p>
          </div>
        </Card>
        <Card span={7} title={`${t("nearby")} (${reports.length})`} icon="📍">
          {reports.length === 0 ? (
            <div className="empty"><div className="leaf" aria-hidden="true">🌳</div><p className="muted">{t("no_reports")}</p></div>
          ) : (
            <div className="stack">
              {reports.map((r, i) => (
                <div key={r.id} className="member" style={{ animation: `rise-in .4s ${i * 50}ms both` }}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <b>{catLabel(r.category)}</b>
                    <span className="tag">
                      {r.status === "confirmed" ? tx("✅ confirmed", "✅ पुष्टि हुई") : tx("⏳ unverified", "⏳ पुष्टि बाकी")}
                      {r.ai_assisted ? " · AI" : ""}
                    </span>
                  </div>
                  <p style={{ margin: "6px 0" }}>{r.description}</p>
                  <div className="row small muted" style={{ justifyContent: "space-between" }}>
                    <span>
                      {new Date(r.created_at * 1000).toLocaleString()} · <span aria-hidden="true">👍</span>
                      <span className="sr-only">{tx("Confirmations:", "पुष्टियाँ:")}</span> {r.confirmations}
                    </span>
                    <button type="button" className="btn ghost small" disabled={confirmed.includes(r.id)} onClick={() => confirm(r.id)}>
                      {t("confirm")}
                    </button>
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
