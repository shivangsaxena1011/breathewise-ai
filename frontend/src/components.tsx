import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, fmtHour, LEVEL_COLORS, type Action, type Hour, type Place } from "./api";
import { AQI_LABELS_HI } from "./i18n";
import { prefersReducedMotion } from "./motion";
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

/** Animate from 0 up to `target` with an ease-out curve; jumps straight there when motion is reduced. */
export function useCountUp(target: number | null, ms = 1400): number {
  const [v, setV] = useState(0);
  const reduced = prefersReducedMotion();
  useEffect(() => {
    if (target == null || reduced) return;
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / ms);
      setV(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms, reduced]);
  return reduced ? target ?? 0 : v;
}

/** AQI category label in the UI language. */
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

/** City search with debounced geocoding. Arrow keys move between results; Escape returns to the field. */
export function CitySearch({ onPick }: { onPick: (p: Place) => void }) {
  const { t, tx, lang } = useApp();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Place[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const keepClosed = useRef(false); // set when we move focus back to the field ourselves
  const tRef = useRef(t); // read the latest translator without re-running the search on every app update
  useEffect(() => { tRef.current = t; }, [t]);

  const term = q.trim();
  const shown = term.length >= 2 ? results : [];
  useEffect(() => {
    if (term.length < 2) return;
    let stale = false; // an older, slower response must not overwrite results for newer text
    const timer = window.setTimeout(() => {
      api.geocode(term, lang)
        .then((r) => {
          if (stale) return;
          setResults(r.results);
          setOpen(true);
          if (r.results.length === 0) setMsg(tRef.current("no_city"));
        })
        .catch((e: unknown) => { if (!stale) setMsg((e as Error).message); });
    }, 300);
    return () => { stale = true; window.clearTimeout(timer); };
  }, [term, lang]);

  const pick = (p: Place) => { onPick(p); setQ(""); setResults([]); setOpen(false); };
  const locate = () => {
    if (!navigator.geolocation) { setMsg(t("no_geo")); return; }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setBusy(false);
        pick({ name: t("my_location"), lat: +pos.coords.latitude.toFixed(3), lon: +pos.coords.longitude.toFixed(3) });
      },
      () => { setBusy(false); setMsg(t("geo_denied")); },
      { timeout: 10000 },
    );
  };
  // Close the list once focus leaves the whole search widget (field + results).
  const closeIfOutside = (e: React.FocusEvent) => {
    if (!wrapRef.current?.contains(e.relatedTarget as Node | null)) setOpen(false);
  };
  const resultButtons = () => Array.from(wrapRef.current?.querySelectorAll<HTMLButtonElement>("#city-results button") ?? []);
  const onResultKey = (e: React.KeyboardEvent, i: number) => {
    const buttons = resultButtons();
    if (e.key === "ArrowDown") { e.preventDefault(); buttons[Math.min(i + 1, buttons.length - 1)]?.focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); (i === 0 ? inputRef.current : buttons[i - 1])?.focus(); }
    if (e.key === "Escape") {
      e.preventDefault(); // keep the typed text: a search field clears itself on Escape
      keepClosed.current = true;
      setOpen(false);
      inputRef.current?.focus();
    }
  };
  const listOpen = open && shown.length > 0;

  return (
    <div className="stack">
      <div className="row">
        <div className="search" ref={wrapRef} style={{ flex: 1, minWidth: 200 }}>
          <label className="sr-only" htmlFor="city">{t("search_city")}</label>
          <input id="city" ref={inputRef} type="search" placeholder={`🔍 ${t("search_city")}`} value={q} autoComplete="off"
            aria-controls="city-results" aria-describedby="city-count"
            onChange={(e) => { setQ(e.target.value); setMsg(null); }}
            onFocus={() => {
              if (keepClosed.current) keepClosed.current = false;
              else setOpen(true);
            }}
            onBlur={closeIfOutside}
            onKeyDown={(e) => {
              if (e.key === "Enter" && shown[0]) pick(shown[0]);
              if (e.key === "ArrowDown" && listOpen) { e.preventDefault(); resultButtons()[0]?.focus(); }
              if (e.key === "Escape") setOpen(false);
            }} />
          <span id="city-count" className="sr-only" aria-live="polite">
            {listOpen ? tx(`${shown.length} places found. Use the down arrow to browse.`,
              `${shown.length} जगहें मिलीं। देखने के लिए नीचे वाला तीर दबाएँ।`) : ""}
          </span>
          {listOpen && (
            <ul id="city-results" aria-label={t("search_city")}>
              {shown.map((r, i) => (
                <li key={`${r.lat},${r.lon}`}>
                  <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(r)}
                    onKeyDown={(e) => onResultKey(e, i)} onBlur={closeIfOutside}>
                    <b>{r.name}</b> <span className="muted small">{[r.admin1, r.country].filter(Boolean).join(", ")}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <button type="button" className="btn ghost" onClick={locate} disabled={busy} aria-busy={busy}>
          <span aria-hidden="true">📍</span> {t("use_location")}
        </button>
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
  // Follow outside changes to `value` by adjusting state during render (React's recommended pattern, not an effect).
  const [synced, setSynced] = useState(value);
  if (synced !== value) {
    setSynced(value);
    setText((t) => (Number(t) === value && t !== "" ? t : String(value)));
  }
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

/** Primary button that shows a spinner (announced as "Please wait…") while `busy`. */
export function Btn({ busy, children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean }) {
  const { t } = useApp();
  return (
    <button type="button" className="btn" {...rest} disabled={busy || rest.disabled} aria-busy={busy || undefined}>
      {busy
        ? <><span className="spinner" aria-hidden="true" /><span className="sr-only" role="status">{t("busy")}</span></>
        : children}
    </button>
  );
}
