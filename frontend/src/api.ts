// Typed client for the BreatheWise backend.

export type Lang = "en" | "hi";
export type AgeGroup = "infant" | "child" | "teen" | "adult" | "elderly";
export type Condition = "asthma" | "copd" | "heart" | "pregnant" | "allergy" | "diabetes";
export type Mode =
  | "car_petrol" | "car_diesel" | "car_cng" | "car_ev" | "two_wheeler" | "e_two_wheeler"
  | "auto_cng" | "bus" | "metro" | "cycle" | "walk";

export interface Place { name: string; lat: number; lon: number; admin1?: string; country?: string }
export interface Member {
  name: string; age_group: AgeGroup; conditions: Condition[]; outdoor_hours: number;
  exercises_outdoors: boolean; commute_mode?: Mode | null;
}
export interface Home {
  has_purifier: boolean; cooking_fuel: "lpg" | "png" | "induction" | "biomass" | "kerosene";
  smoker_at_home: boolean; burns_incense: boolean; has_pets: boolean;
}
export interface Household { members: Member[]; home: Home }

export interface Hour { time: string; pm2_5: number | null; pm10: number | null; level: number; us_aqi: number | null }
export interface Window { date: string; best: { start: string; pm2_5: number; level: number }; worst: { start: string; pm2_5: number; level: number } }
export interface Source { name: string; url: string; kind: string; note: string }
export interface Aqi {
  value: number | null; scale: string; label: string; category: string | null; level: number | null; color: string; health: string;
  dominant: string | null; sub_indices: Record<string, number>; us_aqi: number | null; basis?: "model" | "station_calibrated";
}
export interface Snapshot {
  observed_at: string; fetched_at: string; aqi: Aqi;
  pollutants_now: Record<string, number | null>; averages: Record<string, number | null>;
  weather_now: Record<string, number | null>; smog_drivers: { key: string; text: string }[];
  hourly: Hour[]; now_index: number; windows: Window[]; source: Source;
  location: { lat: number; lon: number; timezone: string };
  station: Station | null;
}
export interface Station {
  name: string; distance_km: number; measured_at: string; age_minutes: number;
  us_aqi: number; pm25: number | null; pm10: number | null; dominant: string | null;
  attributions: { name: string; url: string }[];
  calibration: { pm2_5: number | null; pm10: number | null };
}
export interface Action { text: string; why: string; priority: "high" | "medium" | "low" }

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("You seem to be offline.", 0);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(errorMessage(body, res.status), res.status);
  return body as T;
}

/** Readable message from an API error body. FastAPI validation errors arrive as a list. */
export function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  const first = Array.isArray(detail) ? (detail[0] as { loc?: unknown[]; msg?: string } | undefined) : undefined;
  if (first?.msg) return `${first.loc?.slice(-1)[0] ?? "Input"}: ${first.msg}`;
  if (status === 429) return "Too many requests — please wait a minute.";
  return "Something went wrong. Please try again.";
}

const post = <T,>(path: string, data: unknown) =>
  request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

const q = (o: Record<string, string | number>) => new URLSearchParams(Object.entries(o).map(([k, v]) => [k, String(v)])).toString();

export const api = {
  health: () => request<{ ai: boolean; model: string | null }>("/api/health"),
  geocode: (name: string, lang: Lang) => request<{ results: Place[] }>(`/api/geocode?${q({ q: name, lang })}`),
  air: (p: Place) => request<Snapshot>(`/api/air?${q({ lat: p.lat, lon: p.lon })}`),
  grid: (p: Place) => request<{ cells: { lat: number; lon: number; pm2_5: number | null; level: number; color: string }[] }>(
    `/api/air/grid?${q({ lat: p.lat, lon: p.lon })}`),
  plan: (p: Place, household: Household, lang: Lang) => post<any>("/api/plan/family", { lat: p.lat, lon: p.lon, household, lang }),
  routine: (p: Place, household: Household, lang: Lang) => post<any>("/api/routine", { lat: p.lat, lon: p.lon, household, lang,
    commute_mode: household.members.find((m) => m.commute_mode)?.commute_mode ?? null }),
  indoor: (p: Place, home: Home, rooms: { kind: string; area_m2: number }[], lang: Lang) =>
    post<any>("/api/indoor", { lat: p.lat, lon: p.lon, home, rooms, lang }),
  alerts: (p: Place, activities: unknown[], household: Household) =>
    post<any>("/api/alerts", { lat: p.lat, lon: p.lon, activities, household }),
  mobility: (distance_km: number, occupants: number) => post<any>("/api/mobility", { distance_km, occupants }),
  whatIf: (body: unknown) => post<any>("/api/whatif", body),
  chat: (body: unknown) => post<{ reply: string; mode: "ai" | "rules" }>("/api/chat", body),
  reports: (p: Place) => request<{ reports: any[] }>(`/api/reports?${q({ lat: p.lat, lon: p.lon })}`),
  addReport: (body: unknown) => post<any>("/api/reports", body),
  confirmReport: (id: number) => post<any>(`/api/reports/${id}/confirm`, {}),
  analyzePhoto: async (file: File, lang: Lang) => {
    const fd = new FormData();
    fd.append("photo", file);
    fd.append("lang", lang);
    return request<any>("/api/reports/analyze", { method: "POST", body: fd });
  },
};

export const LEVEL_COLORS = ["#2e9d5b", "#8cbf3f", "#e0b000", "#e8772e", "#d63a3a", "#7e2a8c"];

export function fmtHour(iso?: string | null): string {
  if (!iso) return "—";
  const h = Number(iso.slice(11, 13));
  return `${h % 12 || 12} ${h < 12 ? "AM" : "PM"}`;
}
