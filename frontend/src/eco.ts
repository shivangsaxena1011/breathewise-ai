// Eco tracker logic: pure functions, so it is unit-tested without a browser.

export interface EcoLog { id: string; date: string; label: string; kg: number; kind?: string }

/** YYYY-MM-DD in the user's own timezone (toISOString() is UTC, which is the wrong day in India before 5:30 AM). */
export function localDate(d: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// Factors match the backend (services/emissions.py): petrol 2.31 kg CO₂/L at 15 km/L, metro ≈0.03 kg/pkm, grid 0.72 kg/kWh.
const CAR_KG_PER_KM = 2.31 / 15;

/** Quick actions. Each has a stable `kind` so challenges work in any UI language.
 *  kg = CO₂ avoided compared with making the same trip alone by petrol car. */
export const QUICK = [
  { kind: "transit", en: "🚇 Metro/bus instead of car (10 km)", hi: "🚇 कार की जगह मेट्रो/बस (10 किमी)", kg: +(10 * (CAR_KG_PER_KM - 0.03)).toFixed(2) },
  { kind: "active", en: "🚲 Cycled/walked instead of driving (3 km)", hi: "🚲 कार की जगह पैदल/साइकिल (3 किमी)", kg: +(3 * CAR_KG_PER_KM).toFixed(2) },
  { kind: "carpool", en: "🤝 Carpooled (3 people, 15 km)", hi: "🤝 कारपूल (3 लोग, 15 किमी)", kg: +(15 * CAR_KG_PER_KM * (2 / 3)).toFixed(2) },
  { kind: "idle", en: "🚦 Switched off engine at signals", hi: "🚦 सिग्नल पर इंजन बंद किया", kg: 0.1 },
  { kind: "compost", en: "🍂 Composted leaves instead of burning", hi: "🍂 पत्ते जलाने की जगह खाद बनाई", kg: 0 },
  { kind: "energy", en: "💡 Saved 2 kWh electricity", hi: "💡 2 kWh बिजली बचाई", kg: +(2 * 0.72).toFixed(2) },
] as const;

// Logs saved before `kind` existed are matched by their old English label.
const LEGACY: Record<string, string> = {
  "🚇 Metro/bus instead of car (10 km)": "transit", "🚲 Cycled/walked a 3 km errand": "active",
  "🤝 Carpooled (3 people, 15 km)": "carpool", "🚦 Switched off engine at signals": "idle",
  "🍂 Composted leaves instead of burning": "compost", "💡 Saved 2 kWh electricity": "energy",
};

export const kindOf = (l: Pick<EcoLog, "kind" | "label">): string => l.kind ?? LEGACY[l.label] ?? "";

export function logLabel(l: Pick<EcoLog, "kind" | "label">, lang: string): string {
  const q = QUICK.find((x) => x.kind === kindOf(l));
  return q ? (lang === "hi" ? q.hi : q.en) : l.label;
}

export const CHALLENGES = [
  { id: "car-free", en: "🚇 3 car-free commutes", hi: "🚇 3 बार बिना कार सफ़र", need: 3, kinds: ["transit", "active", "carpool"] },
  { id: "no-burn", en: "🍂 Zero burning week", hi: "🍂 बिना जलाए सप्ताह", need: 1, kinds: ["compost"] },
  { id: "idle", en: "🚦 5 idle-free signals", hi: "🚦 5 सिग्नल पर इंजन बंद", need: 5, kinds: ["idle"] },
] as const;

export function challengeProgress(c: (typeof CHALLENGES)[number], weekLogs: EcoLog[]) {
  const n = weekLogs.filter((l) => (c.kinds as readonly string[]).includes(kindOf(l))).length;
  return { count: Math.min(n, c.need), done: n >= c.need, ratio: Math.min(1, n / c.need) };
}

/** Last 7 days (oldest first), this week's total, and the day streak. */
export function weekStats(logs: EcoLog[], today: Date = new Date(), locale = "en-IN") {
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(today);
    d.setDate(today.getDate() - (6 - i));
    const key = localDate(d);
    return {
      key,
      day: d.toLocaleDateString(locale, { weekday: "narrow" }),
      kg: logs.filter((l) => l.date === key).reduce((s, l) => s + l.kg, 0),
    };
  });
  const weekLogs = logs.filter((l) => l.date >= days[0].key && l.date <= days[6].key);
  // Streak = consecutive days with an action, counting back from today, or from yesterday if nothing
  // is logged yet today (so the streak isn't "lost" first thing in the morning).
  const logged = new Set(logs.map((l) => l.date));
  const cursor = new Date(today);
  if (!logged.has(localDate(cursor))) cursor.setDate(cursor.getDate() - 1);
  let streak = 0;
  while (logged.has(localDate(cursor)) && streak < 3650) {
    streak++;
    cursor.setDate(cursor.getDate() - 1);
  }
  return { days, weekLogs, week: weekLogs.reduce((s, l) => s + l.kg, 0), streak };
}
