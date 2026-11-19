import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type Household, type Lang, type Place, type Snapshot } from "./api";
import { localDate, type EcoLog } from "./eco";
import { translate, type Key } from "./i18n";

export { localDate, type EcoLog };

/** crypto.randomUUID only exists in secure contexts (HTTPS/localhost); fall back elsewhere (e.g. LAN testing on a phone). */
function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}
function save(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage full or blocked */ }
}

export const DEFAULT_HOUSEHOLD: Household = {
  members: [
    { name: "Me", age_group: "adult", conditions: [], outdoor_hours: 1, exercises_outdoors: true, commute_mode: "two_wheeler" },
  ],
  home: { has_purifier: false, cooking_fuel: "lpg", smoker_at_home: false, burns_incense: false, has_pets: false },
};

interface Ctx {
  lang: Lang; setLang: (l: Lang) => void; t: (k: Key) => string;
  /** Inline bilingual text for short labels that don't need a dictionary key. */
  tx: (en: string, hi: string) => string;
  place: Place | null; setPlace: (p: Place) => void;
  snap: Snapshot | null; loading: boolean; error: string | null; offlineSince: string | null; refresh: () => void;
  household: Household; setHousehold: (h: Household) => void;
  logs: EcoLog[]; addLog: (l: Omit<EcoLog, "id" | "date">) => void; removeLog: (id: string) => void;
  ai: boolean;
}

const AppCtx = createContext<Ctx | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => load("bw.lang", "en"));
  const [place, setPlaceState] = useState<Place | null>(() => load("bw.place", null));
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offlineSince, setOfflineSince] = useState<string | null>(null);
  const [household, setHouseholdState] = useState<Household>(() => load("bw.household", DEFAULT_HOUSEHOLD));
  const [logs, setLogs] = useState<EcoLog[]>(() => load("bw.logs", []));
  const [ai, setAi] = useState(false);

  useEffect(() => { api.health().then((h) => setAi(h.ai)).catch(() => setAi(false)); }, []);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);

  const latest = useRef(0);
  const snapFor = useRef<string | null>(null);
  const fetchAir = useCallback(async (p: Place) => {
    const id = ++latest.current; // ignore responses for a city the user already switched away from
    setLoading(true);
    setError(null);
    const key = `${p.lat},${p.lon}`;
    if (snapFor.current !== key) { setSnap(null); setOfflineSince(null); } // don't show the old city's numbers
    try {
      const s = await api.air(p);
      if (id !== latest.current) return;
      snapFor.current = key;
      setSnap(s);
      setOfflineSince(null);
      save("bw.lastSnap", { place: p, snap: s });
    } catch (e) {
      if (id !== latest.current) return;
      const cached = load<{ place: Place; snap: Snapshot } | null>("bw.lastSnap", null);
      if (cached && cached.place.lat === p.lat && cached.place.lon === p.lon) {
        snapFor.current = key;
        setSnap(cached.snap);
        setOfflineSince(cached.snap.fetched_at);
      } else {
        setError((e as Error).message);
      }
    } finally {
      if (id === latest.current) setLoading(false);
    }
  }, []);

  useEffect(() => { if (place) fetchAir(place); }, [place, fetchAir]);

  const value = useMemo<Ctx>(() => ({
    lang,
    setLang: (l) => { setLangState(l); save("bw.lang", l); },
    t: (k) => translate(lang, k),
    tx: (en, hi) => (lang === "hi" ? hi : en),
    place,
    setPlace: (p) => { setPlaceState(p); save("bw.place", p); },
    snap, loading, error, offlineSince,
    refresh: () => { if (place) fetchAir(place); },
    household,
    setHousehold: (h) => { setHouseholdState(h); save("bw.household", h); },
    logs,
    addLog: (l) => setLogs((prev) => {
      const next = [{ ...l, id: newId(), date: localDate() }, ...prev].slice(0, 500);
      save("bw.logs", next);
      return next;
    }),
    removeLog: (id) => setLogs((prev) => { const next = prev.filter((x) => x.id !== id); save("bw.logs", next); return next; }),
    ai,
  }), [lang, place, snap, loading, error, offlineSince, household, logs, ai, fetchAir]);

  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

export function useApp(): Ctx {
  const ctx = useContext(AppCtx);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}
