import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, fmtHour, LEVEL_COLORS, type Action, type Hour, type Place } from "./api";
import { AQI_LABELS_HI } from "./i18n";
import { useApp } from "./store";

export function Sky() {
  const particles = Array.from({ length: 8 }, (_, i) => i);
  return (
    <div className="sky" aria-hidden="true">
      <div className="blob b1" /><div className="blob b2" /><div className="blob b3" />
      {particles.map((i) => (
        <span key={i} className="particle" style={{
          left: `${(i * 73) % 100}%`, animationDuration: `${14 + (i % 5) * 4}s`, animationDelay: `${-i * 1.7}s`,
          width: 4 + (i % 3) * 3, height: 4 + (i % 3) * 3,
        }} />
      ))}
    </div>
  );
}

export function useCountUp(target: number | null, ms = 1400): number {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (target == null) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) { setV(target); return; }
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / ms);
      setV(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

export function aqiLabel(label: string, lang: string) {
  return lang === "hi" ? AQI_LABELS_HI[label] ?? label : label;
}

export function AqiRing({ value, label }: { value: number | null; label: string }) {
  const n = useCountUp(value);
  const r = 80, c = 2 * Math.PI * r;
  const [shown, setShown] = useState(0);
  useEffect(() => { const id = setTimeout(() => setShown(Math.min(1, (value ?? 0) / 500)), 60); return () => clearTimeout(id); }, [value]);
  return (
    <div className="ring" role="img" aria-label={`AQI ${value ?? "unavailable"}, ${label}`}>
      <div className="pulse" />
      <svg width="190" height="190" viewBox="0 0 190 190">
        <circle className="track" cx="95" cy="95" r={r} fill="none" strokeWidth="14" />
        <circle className="bar" cx="95" cy="95" r={r} fill="none" strokeWidth="14"
          strokeDasharray={c} strokeDashoffset={c * (1 - shown)} />
      </svg>
      <div className="inner">
        <div className="num">{value == null ? "—" : n}</div>
        <div className="small muted">AQI</div>
      </div>
    </div>
  );
}

export function ForecastBars({ hours, nowIndex }: { hours: Hour[]; nowIndex: number }) {
  const { tx } = useApp();
  const slice = hours.slice(nowIndex, nowIndex + 24);
  const max = Math.max(60, ...slice.map((h) => h.pm2_5 ?? 0));
  return (
    <div>
      <div className="bars" role="img" aria-label={tx("PM2.5 forecast for the next 24 hours", "अगले 24 घंटों का PM2.5 पूर्वानुमान")}>
        {slice.map((h, i) => (
          <div key={h.time} className={`b ${i === 0 ? "now" : ""}`}
            title={`${fmtHour(h.time)} · PM2.5 ${h.pm2_5?.toFixed(0) ?? "?"} µg/m³`}
            style={{ height: `${((h.pm2_5 ?? 0) / max) * 100}%`, background: LEVEL_COLORS[h.level], animationDelay: `${i * 25}ms` }} />
        ))}
      </div>
      <div className="bars-x">
        {slice.filter((_, i) => i % 6 === 0).map((h) => <span key={h.time}>{fmtHour(h.time)}</span>)}
      </div>
    </div>
  );
}

const PRIORITY_ICON = { high: "⚠️", medium: "💡", low: "🌿" } as const;

export function ActionList({ items }: { items: Action[] }) {
  const { t } = useApp();
  return (
    <div className="stack">
      {items.map((a, i) => (
        <div key={i} className={`action ${a.priority}`} style={{ animationDelay: `${i * 50}ms` }}>
          <div className="ico" aria-hidden="true">{PRIORITY_ICON[a.priority]}</div>
          <div>
            <div>{a.text}</div>
            <details><summary>{t("why")}</summary><p>{a.why}</p></details>
          </div>
        </div>
      ))}
    </div>
  );
}

export function CitySearch({ onPick }: { onPick: (p: Place) => void }) {
  const { t, lang } = useApp();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Place[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const timer = useRef<number>(0);

  const [open, setOpen] = useState(false);
  const tRef = useRef(t); // read the latest translator without re-running the search on every app update
  tRef.current = t;
  useEffect(() => {
    window.clearTimeout(timer.current);
    if (q.trim().length < 2) { setResults([]); return; }
    let stale = false; // an older, slower response must not overwrite results for newer text
    timer.current = window.setTimeout(() => {
      api.geocode(q.trim(), lang)
        .then((r) => {
          if (stale) return;
          setResults(r.results);
          setOpen(true);
          if (r.results.length === 0) setMsg(tRef.current("no_city"));
        })
        .catch((e) => { if (!stale) setMsg(e.message); });
    }, 300);
    return () => { stale = true; window.clearTimeout(timer.current); };
  }, [q, lang]);

  const pick = (p: Place) => { onPick(p); setQ(""); setResults([]); setOpen(false); };
  const locate = () => {
    if (!navigator.geolocation) { setMsg(t("no_geo")); return; }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => { setBusy(false); pick({ name: t("my_location"), lat: +pos.coords.latitude.toFixed(3), lon: +pos.coords.longitude.toFixed(3) }); },
      () => { setBusy(false); setMsg(t("geo_denied")); },
      { timeout: 10000 },
    );
  };

  return (
    <div className="stack">
      <div className="row">
        <div className="search" style={{ flex: 1, minWidth: 200 }}
          onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false); }}>
          <label className="sr-only" htmlFor="city">{t("search_city")}</label>
          <input id="city" type="search" role="combobox" placeholder={`🔍 ${t("search_city")}`} value={q} autoComplete="off"
            aria-expanded={open && results.length > 0} aria-controls="city-results" aria-autocomplete="list"
            onChange={(e) => { setQ(e.target.value); setMsg(null); }}
            onFocus={() => setOpen(true)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && results[0]) pick(results[0]);
              if (e.key === "Escape") setOpen(false);
            }} />
          {open && results.length > 0 && (
            <ul id="city-results" aria-label={t("search_city")}>
              {results.map((r) => (
                <li key={`${r.lat},${r.lon}`}>
                  <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(r)}>
                    <b>{r.name}</b> <span className="muted small">{[r.admin1, r.country].filter(Boolean).join(", ")}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <button type="button" className="btn ghost" onClick={locate} disabled={busy}>📍 {t("use_location")}</button>
      </div>
      {msg && <div className="notice warn" role="alert">{msg}</div>}
    </div>
  );
}

export function Card({ title, icon, span = 12, children, className = "" }:
  { title?: string; icon?: string; span?: number; children: ReactNode; className?: string }) {
  return (
    <section className={`card span-${span} ${className}`}>
      {title && <h3><span aria-hidden="true">{icon}</span>{title}</h3>}
      {children}
    </section>
  );
}

export function NeedPlace() {
  const { t } = useApp();
  return (
    <div className="card empty">
      <div className="leaf" aria-hidden="true">🍃</div>
      <p>{t("pick_city_first")}</p>
    </div>
  );
}

export function Assumptions({ items }: { items: string[] }) {
  const { t } = useApp();
  return (
    <details className="small muted" style={{ marginTop: 8 }}>
      <summary style={{ cursor: "pointer" }}>{t("assumptions")}</summary>
      <ul>{items.map((a) => <li key={a}>{a}</li>)}</ul>
    </details>
  );
}

/** Number field that lets people clear and retype, then clamps to [min, max] when they leave the field. */
export function NumInput({ value, onChange, min, max, step = 1 }:
  { value: number; onChange: (n: number) => void; min: number; max: number; step?: number }) {
  const [text, setText] = useState(String(value));
  useEffect(() => { setText((t) => (Number(t) === value && t !== "" ? t : String(value))); }, [value]);
  const commit = () => {
    const n = Number(text);
    const clamped = text.trim() !== "" && Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : value;
    setText(String(clamped));
    if (clamped !== value) onChange(clamped);
  };
  return (
    <input type="number" inputMode="decimal" min={min} max={max} step={step} value={text}
      onChange={(e) => {
        setText(e.target.value);
        const n = e.target.valueAsNumber;
        if (Number.isFinite(n) && n >= min && n <= max) onChange(n);
      }}
      onBlur={commit} />
  );
}

export function Btn({ busy, children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean }) {
  return (
    <button className="btn" {...rest} disabled={busy || rest.disabled}>
      {busy ? <span className="spinner" role="status" aria-label="…" /> : children}
    </button>
  );
}
