// Typed client for the BreatheWise backend. Response types mirror backend/app/services/*.

// ----------------------------------------------------------------------------- shared vocabulary
export type Lang = "en" | "hi";
export type AgeGroup = "infant" | "child" | "teen" | "adult" | "elderly";
export type Condition = "asthma" | "copd" | "heart" | "pregnant" | "allergy" | "diabetes";
export type Mode =
  | "car_petrol" | "car_diesel" | "car_cng" | "car_ev" | "two_wheeler" | "e_two_wheeler"
  | "auto_cng" | "bus" | "metro" | "cycle" | "walk";
export type CookingFuel = "lpg" | "png" | "induction" | "biomass" | "kerosene";
export type RoomKind = "kitchen" | "bedroom" | "living" | "kids" | "study" | "bathroom";
export type ReportCategory =
  | "waste_burning" | "construction_dust" | "industrial_smoke" | "vehicle_smoke" | "traffic_jam" | "crop_burning" | "other";
export type Priority = "high" | "medium" | "low";
/** Stable English keys from the risk engine; the UI translates them. */
export type RiskLabel = "Low" | "Moderate" | "High" | "Very high" | "Extreme";

// ----------------------------------------------------------------------------- request models
export interface Place { name: string; lat: number; lon: number; admin1?: string; country?: string }
export interface Member {
  name: string; age_group: AgeGroup; conditions: Condition[]; outdoor_hours: number;
  exercises_outdoors: boolean; commute_mode?: Mode | null;
}
export interface Home {
  has_purifier: boolean; cooking_fuel: CookingFuel;
  smoker_at_home: boolean; burns_incense: boolean; has_pets: boolean;
}
export interface Household { members: Member[]; home: Home }
export interface RoomInput { kind: RoomKind; area_m2: number }
export interface ActivityInput { title: string; start: string; duration_min: number; who?: string; sensitive: boolean }
export interface ChatTurn { role: "user" | "assistant"; content: string }
export interface ChatRequest {
  message: string; history: ChatTurn[]; lat?: number; lon?: number; place?: string;
  household?: Household; lang: Lang;
}
export interface WhatIfRequest {
  lat?: number; lon?: number; lang: Lang; explain: boolean;
  mode_shift?: { from_mode: Mode; to_mode: Mode; distance_km_one_way: number; days_per_week: number; occupants?: number };
  exercise_shift?: { current_hour: number; duration_min: number; intensity: "light" | "moderate" | "vigorous" };
  waste_burning?: { kg_per_week: number };
  energy_saving?: { kwh_per_month: number };
}
export interface NewReport { category: ReportCategory; description: string; lat: number; lon: number; ai_assisted: boolean }

// ----------------------------------------------------------------------------- air snapshot
export interface Hour { time: string; pm2_5: number | null; pm10: number | null; level: number; us_aqi: number | null }
export interface WindowSlot { start: string; pm2_5: number; level: number }
/** Cleanest and dirtiest 2-hour daytime windows for one day (or the rolling next 24 h). */
export interface DayWindow { date: string; best: WindowSlot; worst: WindowSlot }
export interface Source { name: string; url: string; kind: string; note: string }
export interface Aqi {
  value: number | null; scale: string; label: string; category: string | null; level: number | null; color: string; health: string;
  dominant: string | null; sub_indices: Record<string, number>; us_aqi: number | null; basis?: "model" | "station_calibrated";
}
export interface Station {
  name: string; distance_km: number; measured_at: string; age_minutes: number;
  us_aqi: number; pm25: number | null; pm10: number | null; dominant: string | null;
  attributions: { name: string; url: string }[];
  calibration: { pm2_5: number | null; pm10: number | null };
}
export interface Snapshot {
  observed_at: string; fetched_at: string; aqi: Aqi;
  pollutants_now: Record<string, number | null>; averages: Record<string, number | null>;
  weather_now: Record<string, number | null>; smog_drivers: { key: string; text: string }[];
  hourly: Hour[]; now_index: number; windows: DayWindow[]; source: Source;
  location: { lat: number; lon: number; timezone: string };
  station: Station | null;
}
export interface GridCell { lat: number; lon: number; pm2_5: number | null; pm10: number | null; level: number; color: string }
export interface AreaGrid { center: { lat: number; lon: number }; step_deg: number; cells: GridCell[]; source: Source }

// ----------------------------------------------------------------------------- family & daily life
export interface Action { text: string; why: string; priority: Priority }
export interface Tip { text: string; why: string }
export interface PlanMember {
  name: string; age_group: AgeGroup;
  risk: { score: number; label: RiskLabel; factors: string[] };
  actions: Action[];
}
/** Gemini's rewrite of the rule-based plan; null when AI is off or unavailable. */
export interface AiPlan { summary: string; members: { name: string; headline: string; tips: string[] }[]; impact: string }
export interface FamilyPlan {
  air_level: number; aqi: Aqi; best_window: string | null; worst_window: string | null;
  household_risk: RiskLabel; most_at_risk: string; members: PlanMember[]; household_actions: Action[];
  explanation: { data_used: string[]; method: string; reliability: string };
  source: Source; ai: AiPlan | null;
}
export interface RoutineStep { time: string; title: string; detail: string }
export interface Routine {
  steps: RoutineStep[]; air_level: number; best_window: string | null; worst_window: string | null; aqi: Aqi; source: Source;
}
export type Verdict = "open" | "brief" | "closed";
export interface IndoorReport {
  ventilation: { verdict: Verdict; text: string; now_pm2_5: number | null; best_window: WindowSlot | null; why: string };
  rooms: { kind: RoomKind; tips: Tip[]; purifier: { volume_m3: number; cadr_m3h: number; cadr_cfm: number; basis: string } }[];
  general: Tip[]; aqi: Aqi; source: Source;
}
export interface ActivityAlert {
  activity: string; start: string; status: "ok" | "warn" | "unknown"; message: string;
  who?: string | null; pm2_5?: number | null; level?: number; category?: string; suggested_time?: string;
}
export interface AlertsResponse { alerts: ActivityAlert[]; source: Source; observed_at: string }

// ----------------------------------------------------------------------------- impact
export interface TripRow {
  mode: Mode; label: string; kg_co2_per_person: number; basis: string; local_pollution: string; relative: number;
}
export interface TripComparison { distance_km: number; occupants: number; rows: TripRow[]; exposure_note: string }
export interface ModeShiftResult {
  km_per_week: number; kg_co2_week_before: number; kg_co2_week_after: number;
  kg_co2_saved_week: number; kg_co2_saved_year: number; assumptions: string[];
}
export interface ExposureSlot { time: string; pm2_5: number; dose_ug: number }
export type ExerciseShiftResult =
  | { available: false; reason?: string }
  | { available: true; usual: ExposureSlot; best: ExposureSlot; dose_reduction_pct: number; assumptions: string[] };
export interface WhatIfResponse {
  results: {
    mode_shift?: ModeShiftResult;
    exercise_shift?: ExerciseShiftResult;
    waste_burning?: { pm25_g_avoided_year: number; assumptions: string[] };
    energy_saving?: { kg_co2_saved_year: number; assumptions: string[] };
  };
  explanation: string | null;
  disclaimer: string;
}

// ----------------------------------------------------------------------------- assistant & community
export interface ChatReply { reply: string; mode: "ai" | "rules"; grounded_on: string[] }
export interface Report {
  id: number; category: ReportCategory; description: string; lat: number; lon: number;
  created_at: number; confirmations: number; ai_assisted: boolean; status: "confirmed" | "unverified";
}
export interface PhotoAnalysis {
  category: ReportCategory | "not_pollution"; visible_signs: string[]; severity: "low" | "medium" | "high" | "unclear";
  suggested_description: string; confidence: "low" | "medium" | "high"; note: string;
}
export interface Health { status: string; ai: boolean; stations: boolean; reports_storage: string; model: string | null }

// ----------------------------------------------------------------------------- transport
export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("You seem to be offline.", 0);
  }
  const body: unknown = await res.json().catch(() => ({}));
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

/** Build a query string from plain values. */
export const query = (params: Record<string, string | number>) =>
  new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();

const at = (p: Place) => query({ lat: p.lat, lon: p.lon });

export const api = {
  health: () => request<Health>("/api/health"),
  geocode: (name: string, lang: Lang) => request<{ results: Place[] }>(`/api/geocode?${query({ q: name, lang })}`),
  air: (p: Place) => request<Snapshot>(`/api/air?${at(p)}`),
  grid: (p: Place) => request<AreaGrid>(`/api/air/grid?${at(p)}`),
  plan: (p: Place, household: Household, lang: Lang) =>
    post<FamilyPlan>("/api/plan/family", { lat: p.lat, lon: p.lon, household, lang }),
  routine: (p: Place, household: Household, lang: Lang) =>
    post<Routine>("/api/routine", {
      lat: p.lat, lon: p.lon, household, lang,
      commute_mode: household.members.find((m) => m.commute_mode)?.commute_mode ?? null,
    }),
  indoor: (p: Place, home: Home, rooms: RoomInput[], lang: Lang) =>
    post<IndoorReport>("/api/indoor", { lat: p.lat, lon: p.lon, home, rooms, lang }),
  alerts: (p: Place, activities: ActivityInput[], household: Household, lang: Lang) =>
    post<AlertsResponse>("/api/alerts", { lat: p.lat, lon: p.lon, activities, household, lang }),
  mobility: (distance_km: number, occupants: number) => post<TripComparison>("/api/mobility", { distance_km, occupants }),
  whatIf: (body: WhatIfRequest) => post<WhatIfResponse>("/api/whatif", body),
  chat: (body: ChatRequest) => post<ChatReply>("/api/chat", body),
  reports: (p: Place) => request<{ reports: Report[] }>(`/api/reports?${at(p)}`),
  addReport: (body: NewReport) => post<Report>("/api/reports", body),
  confirmReport: (id: number) => post<Report>(`/api/reports/${id}/confirm`, {}),
  analyzePhoto: (file: File, lang: Lang) => {
    const fd = new FormData();
    fd.append("photo", file);
    fd.append("lang", lang);
    return request<PhotoAnalysis>("/api/reports/analyze", { method: "POST", body: fd });
  },
};

// ----------------------------------------------------------------------------- display helpers
/** Colours for AQI levels 0–5 (Good → Severe), matching the backend categories. */
export const LEVEL_COLORS = ["#2e9d5b", "#8cbf3f", "#e0b000", "#e8772e", "#d63a3a", "#7e2a8c"];

/** Text colour that keeps WCAG AA contrast (≥4.5:1) on a LEVEL_COLORS background. */
export function levelInk(level: number | null | undefined): string {
  return level != null && level >= 4 ? "#ffffff" : "#0b1f1b";
}

/** "2026-11-19T07:00" → "7 AM". */
export function fmtHour(iso?: string | null): string {
  if (!iso) return "—";
  const h = Number(iso.slice(11, 13));
  return `${h % 12 || 12} ${h < 12 ? "AM" : "PM"}`;
}
