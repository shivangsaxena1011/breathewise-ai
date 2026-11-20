import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
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

function getStorage(): Storage | null {
  try {
    return typeof window !== "undefined" && "localStorage" in window ? window.localStorage : null;
  } catch {
    return null;
  }
}

function load<T>(key: string, fallback: T): T {
  try {
    const s = getStorage();
    const raw = s?.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}
function save(key: string, value: unknown) {
  try { getStorage()?.setItem(key, JSON.stringify(value)); } catch { /* storage full or blocked */ }
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

/** Last successful reading, kept so the app still shows something useful offline. */
interface CachedSnap { place: Place; snap: Snapshot }

/** Outcome of one air request, tagged with the place and refresh round it answers. */
interface AirResult { key: string; round: number; snap: Snapshot | null; error: string | null; offlineSince: string | null }

const placeKey = (p: Place) => `${p.lat},${p.lon}`;

export function AppProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => load("bw.lang", "en"));
  const [place, setPlaceState] = useState<Place | null>(() => load("bw.place", null));
  const [household, setHouseholdState] = useState<Household>(() => load("bw.household", DEFAULT_HOUSEHOLD));
  const [logs, setLogs] = useState<EcoLog[]>(() => load("bw.logs", []));
  const [ai, setAi] = useState(false);
  const [round, setRound] = useState(0); // bumped by refresh() to re-fetch the same place
  const [air, setAir] = useState<AirResult | null>(null);

  useEffect(() => { api.health().then((h) => setAi(h.ai)).catch(() => setAi(false)); }, []);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);

  useEffect(() => {
    if (!place) return;
    const key = placeKey(place);
    let stale = false; // ignore responses for a city the user already switched away from
    api.air(place)
      .then((snap) => {
        if (stale) return;
        setAir({ key, round, snap, error: null, offlineSince: null });
        save("bw.lastSnap", { place, snap } satisfies CachedSnap);
      })
      .catch((e: unknown) => {
        if (stale) return;
        const cached = load<CachedSnap | null>("bw.lastSnap", null);
        const usable = cached !== null && placeKey(cached.place) === key;
        setAir({
          key, round,
          snap: usable ? cached.snap : null,
          error: usable ? null : (e as Error).message,
          offlineSince: usable ? cached.snap.fetched_at : null,
        });
      });
    return () => { stale = true; };
  }, [place, round]);

  // Only show a result for the current place, so the old city's numbers never linger.
  const current = place && air?.key === placeKey(place) ? air : null;
  const snap = current?.snap ?? null;
  const error = current?.round === round ? current.error : null;
  const offlineSince = current?.offlineSince ?? null;
  const loading = place !== null && current?.round !== round;

  const value = useMemo<Ctx>(() => ({
    lang,
    setLang: (l) => { setLangState(l); save("bw.lang", l); },
    t: (k) => translate(lang, k),
    tx: (en, hi) => (lang === "hi" ? hi : en),
    place,
    setPlace: (p) => { setPlaceState(p); save("bw.place", p); },
    snap, loading, error, offlineSince,
    refresh: () => setRound((r) => r + 1),
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
  }), [lang, place, snap, loading, error, offlineSince, household, logs, ai]);

  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

export function useApp(): Ctx {
  const ctx = useContext(AppCtx);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}
