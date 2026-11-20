import { useId, useState } from "react";
import {
  api, LEVEL_COLORS, levelInk, type AgeGroup, type Condition, type FamilyPlan, type Member, type Mode, type RiskLabel, type Routine,
} from "../api";
import { ActionList, aqiLabel, Btn, Card, NeedPlace } from "../components";
import { scrollBehavior } from "../motion";
import { useApp } from "../store";

const AGES: [AgeGroup, string, string][] = [["infant", "👶 Infant", "👶 शिशु"], ["child", "🧒 Child", "🧒 बच्चा"],
  ["teen", "🧑 Teen", "🧑 किशोर"], ["adult", "🧑‍💼 Adult", "🧑‍💼 वयस्क"], ["elderly", "👵 Elderly", "👵 बुज़ुर्ग"]];
const CONDITIONS: [Condition, string, string][] = [["asthma", "Asthma", "अस्थमा"], ["copd", "COPD", "COPD"],
  ["heart", "Heart", "हृदय रोग"], ["pregnant", "Pregnant", "गर्भवती"], ["allergy", "Allergy", "एलर्जी"], ["diabetes", "Diabetes", "डायबिटीज़"]];
export const MODES: [Mode, string, string][] = [
  ["walk", "🚶 Walk", "🚶 पैदल"], ["cycle", "🚲 Cycle", "🚲 साइकिल"], ["metro", "🚇 Metro", "🚇 मेट्रो"], ["bus", "🚌 Bus", "🚌 बस"],
  ["auto_cng", "🛺 Auto (CNG)", "🛺 ऑटो (CNG)"], ["two_wheeler", "🛵 Scooter/bike", "🛵 स्कूटर/बाइक"],
  ["e_two_wheeler", "⚡ E-scooter", "⚡ ई-स्कूटर"], ["car_petrol", "🚗 Petrol car", "🚗 पेट्रोल कार"],
  ["car_diesel", "🚙 Diesel car", "🚙 डीज़ल कार"], ["car_cng", "🚗 CNG car", "🚗 CNG कार"], ["car_ev", "🔌 Electric car", "🔌 इलेक्ट्रिक कार"],
];
/** Travel mode label (with icon) in the UI language. */
export const modeLabel = (m: string, lang: string) => {
  const row = MODES.find((x) => x[0] === m);
  return row ? (lang === "hi" ? row[2] : row[1]) : m;
};
const AGE_ICON = Object.fromEntries(AGES.map(([k, v]) => [k, v.split(" ")[0]]));
const RISK_LEVEL: Record<RiskLabel, number> = { Low: 1, Moderate: 2, High: 3, "Very high": 4, Extreme: 5 };
const RISK_HI: Record<RiskLabel, string> = { Low: "कम", Moderate: "मध्यम", High: "ज़्यादा", "Very high": "बहुत ज़्यादा", Extreme: "अत्यधिक" };
const NEW_MEMBER: Member = { name: "", age_group: "child", conditions: [], outdoor_hours: 2, exercises_outdoors: true, commute_mode: null };

/** Edit one household member: name, age, health conditions, time outdoors and commute. */
function MemberEditor({ m, onChange, onRemove }: { m: Member; onChange: (m: Member) => void; onRemove?: () => void }) {
  const { t, lang } = useApp();
  const conditionsId = useId();
  const pick = (en: string, hi: string) => (lang === "hi" ? hi : en);
  const toggle = (c: Condition) =>
    onChange({ ...m, conditions: m.conditions.includes(c) ? m.conditions.filter((x) => x !== c) : [...m.conditions, c] });
  return (
    <div className="member stack">
      <div className="row">
        <label className="field" style={{ flex: 1 }}>{t("name")}
          <input type="text" value={m.name} maxLength={40} placeholder={pick("e.g. Riya", "जैसे: रिया")} required
            aria-invalid={!m.name.trim()} onChange={(e) => onChange({ ...m, name: e.target.value })} /></label>
        <label className="field" style={{ flex: 1 }}>{t("age")}
          <select value={m.age_group} onChange={(e) => onChange({ ...m, age_group: e.target.value as AgeGroup })}>
            {AGES.map(([k, en, hi]) => <option key={k} value={k}>{pick(en, hi)}</option>)}
          </select></label>
        {onRemove && (
          <button type="button" className="icon-btn" aria-label={`${t("remove")} ${m.name}`.trim()} onClick={onRemove}
            style={{ alignSelf: "end" }}>✕</button>
        )}
      </div>
      <div className="field">
        <span id={conditionsId}>{t("conditions")}</span>
        <div className="chips" role="group" aria-labelledby={conditionsId}>
          {CONDITIONS.map(([c, en, hi]) => (
            <button key={c} type="button" className="chip" aria-pressed={m.conditions.includes(c)} onClick={() => toggle(c)}>
              {pick(en, hi)}
            </button>
          ))}
        </div>
      </div>
      <div className="row">
        <label className="field" style={{ flex: 1 }}>{t("outdoor_h")} ({m.outdoor_hours}h)
          <input type="range" min={0} max={12} step={0.5} value={m.outdoor_hours}
            onChange={(e) => onChange({ ...m, outdoor_hours: +e.target.value })} /></label>
        <label className="field" style={{ flex: 1 }}>{t("commute")}
          <select value={m.commute_mode ?? ""}
            onChange={(e) => onChange({ ...m, commute_mode: (e.target.value || null) as Mode | null })}>
            <option value="">—</option>
            {MODES.map(([k, en, hi]) => <option key={k} value={k}>{pick(en, hi)}</option>)}
          </select></label>
      </div>
      <label className="check"><input type="checkbox" checked={m.exercises_outdoors}
        onChange={(e) => onChange({ ...m, exercises_outdoors: e.target.checked })} />{t("exercises")}</label>
    </div>
  );
}

export default function Family() {
  const { t, tx, lang, place, household, setHousehold } = useApp();
  const [plan, setPlan] = useState<FamilyPlan | null>(null);
  const [routine, setRoutine] = useState<Routine | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!place) return <div className="page"><Head /><NeedPlace /></div>;

  const members = household.members;
  const setMembers = (ms: Member[]) => setHousehold({ ...household, members: ms });
  const valid = members.every((m) => m.name.trim().length > 0);

  const run = async () => {
    setBusy(true); setErr(null);
    try {
      const [p, r] = await Promise.all([api.plan(place, household, lang), api.routine(place, household, lang)]);
      setPlan(p); setRoutine(r);
      setTimeout(() => document.getElementById("plan")?.scrollIntoView({ behavior: scrollBehavior(), block: "start" }), 50);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  const aiMember = (name: string) => plan?.ai?.members?.find((x) => x.name === name);
  const riskText = (label: RiskLabel) => (lang === "hi" ? RISK_HI[label] ?? label : label);

  return (
    <div className="page">
      <Head />
      <div className="grid">
        <Card span={12} icon="👨‍👩‍👧" title={`${tx("Household", "परिवार के सदस्य")} (${members.length})`}>
          <div className="grid">
            {members.map((m, i) => (
              <div key={i} className="span-6">
                <MemberEditor m={m} onChange={(nm) => setMembers(members.map((x, j) => (j === i ? nm : x)))}
                  onRemove={members.length > 1 ? () => setMembers(members.filter((_, j) => j !== i)) : undefined} />
              </div>
            ))}
          </div>
          <div className="row" style={{ marginTop: 14 }}>
            {members.length < 12 && (
              <button type="button" className="btn ghost" onClick={() => setMembers([...members, NEW_MEMBER])}>
                <span aria-hidden="true">＋</span> {t("add_member")}
              </button>
            )}
            <Btn busy={busy} onClick={run} disabled={!valid}><span aria-hidden="true">🛡️</span> {t("make_plan")}</Btn>
          </div>
          {!valid && (
            <p className="small muted" style={{ marginBottom: 0 }}>
              <span aria-hidden="true">✏️</span> {tx("Give everyone a name to make the plan.", "योजना बनाने के लिए हर व्यक्ति का नाम लिखें।")}
            </p>
          )}
          {err && <div className="notice warn" role="alert" style={{ marginTop: 10 }}>{err}</div>}
        </Card>

        {plan && (
          <>
            <section id="plan" className="card span-12" aria-live="polite">
              <h3><span aria-hidden="true">🛡️</span> {t("family_title")} · AQI {plan.aqi.value} ({aqiLabel(plan.aqi.label, lang)})</h3>
              {plan.ai?.summary && <p style={{ marginTop: 0 }}><span aria-hidden="true">✨</span> {plan.ai.summary}</p>}
              <p className="small muted" style={{ marginTop: 0 }}>
                {t("most_at_risk")}: <b>{plan.most_at_risk}</b> · {riskText(plan.household_risk)}
              </p>
              <div className="grid">
                {plan.members.map((m, i) => {
                  const ai = aiMember(m.name);
                  const lvl = RISK_LEVEL[m.risk.label] ?? 1;
                  return (
                    <div key={`${m.name}-${i}`} className="member span-6 stack" style={{ animation: `rise-in .5s ${i * 80}ms both` }}>
                      <div className="row" style={{ justifyContent: "space-between" }}>
                        <b style={{ fontSize: "1.1rem" }}><span aria-hidden="true">{AGE_ICON[m.age_group]}</span> {m.name}</b>
                        <span className="badge" style={{ background: LEVEL_COLORS[lvl], color: levelInk(lvl) }}>
                          {t("risk")}: {riskText(m.risk.label)}
                        </span>
                      </div>
                      <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={5} aria-valuenow={m.risk.score}
                        aria-label={`${t("risk")}: ${riskText(m.risk.label)}`}>
                        <span style={{ width: `${(m.risk.score / 5) * 100}%`, background: LEVEL_COLORS[lvl] }} />
                      </div>
                      {ai?.headline && <div><span aria-hidden="true">✨</span> <b>{ai.headline}</b></div>}
                      {ai?.tips?.length ? <ul style={{ margin: 0, paddingLeft: 18 }}>{ai.tips.map((x) => <li key={x}>{x}</li>)}</ul> : null}
                      <ActionList items={m.actions} />
                      {m.risk.factors.length > 0 && (
                        <details className="small muted"><summary style={{ cursor: "pointer" }}>{t("why")}</summary>
                          <ul>{m.risk.factors.map((f) => <li key={f}>{f}</li>)}</ul></details>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>

            <Card title={t("household_steps")} icon="🏠" span={7}>
              <ActionList items={plan.household_actions} />
              {plan.ai?.impact && <div className="notice ok" style={{ marginTop: 12 }}><span aria-hidden="true">🌍</span> {plan.ai.impact}</div>}
              <details className="small muted" style={{ marginTop: 12 }}>
                <summary style={{ cursor: "pointer" }}><span aria-hidden="true">🔍</span> {tx("How this plan was made", "यह योजना कैसे बनी")}</summary>
                <p><b>{tx("Data", "डेटा")}:</b> {plan.explanation.data_used.join(" · ")}</p>
                <p><b>{tx("Method", "तरीका")}:</b> {plan.explanation.method}</p>
                <p><b>{tx("Reliability", "विश्वसनीयता")}:</b> {plan.explanation.reliability}</p>
              </details>
            </Card>

            {routine && (
              <Card title={t("routine")} icon="🗓️" span={5}>
                <ol className="timeline">
                  {routine.steps.map((s, i) => (
                    <li key={`${s.time}-${s.title}`} style={{ animationDelay: `${i * 60}ms` }}>
                      <span className="tm">{s.time}</span><span className="nd" aria-hidden="true" />
                      <div><b>{s.title}</b><div className="small muted">{s.detail}</div></div>
                    </li>
                  ))}
                </ol>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Head() {
  const { t } = useApp();
  return <div className="page-head"><h2>{t("family_title")}</h2><p>{t("family_sub")}</p></div>;
}
