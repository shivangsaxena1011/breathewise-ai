import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type Household, type Lang, type Place, type Snapshot } from "./api";
import { translate, type Key } from "./i18n";

export interface EcoLog { id: string; date: string; label: string; kg: number }

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

  const fetchAir = useCallback(async (p: Place) => {
    setLoading(true);
    setError(null);
    try {
      const s = await api.air(p);
      setSnap(s);
      setOfflineSince(null);
      save("bw.lastSnap", { place: p, snap: s });
    } catch (e) {
      const cached = load<{ place: Place; snap: Snapshot } | null>("bw.lastSnap", null);
      if (cached && cached.place.lat === p.lat && cached.place.lon === p.lon) {
        setSnap(cached.snap);
        setOfflineSince(cached.snap.fetched_at);
      } else {
        setError((e as Error).message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (place) fetchAir(place); }, [place, fetchAir]);

  const value = useMemo<Ctx>(() => ({
    lang,
    setLang: (l) => { setLangState(l); save("bw.lang", l); },
    t: (k) => translate(lang, k),
    place,
    setPlace: (p) => { setPlaceState(p); save("bw.place", p); },
    snap, loading, error, offlineSince,
    refresh: () => { if (place) fetchAir(place); },
    household,
    setHousehold: (h) => { setHouseholdState(h); save("bw.household", h); },
    logs,
    addLog: (l) => setLogs((prev) => {
      const next = [{ ...l, id: crypto.randomUUID(), date: new Date().toISOString().slice(0, 10) }, ...prev].slice(0, 500);
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
