import { describe, expect, it } from "vitest";
import { CHALLENGES, challengeProgress, kindOf, localDate, logLabel, QUICK, weekStats, type EcoLog } from "./eco";

const log = (date: string, kind: string, kg = 1): EcoLog => ({ id: `${date}-${kind}-${Math.random()}`, date, kind, label: kind, kg });

describe("localDate", () => {
  it("uses the local calendar day, not UTC", () => {
    const lateNight = new Date(2026, 10, 19, 23, 59); // local time
    expect(localDate(lateNight)).toBe("2026-11-19");
    expect(localDate(new Date(2026, 0, 5, 0, 1))).toBe("2026-01-05");
  });
});

describe("weekStats", () => {
  const today = new Date(2026, 10, 19, 10, 0);

  it("totals only the last 7 days", () => {
    const s = weekStats([log("2026-11-19", "transit", 2), log("2026-11-13", "idle", 1), log("2026-11-12", "idle", 50)], today);
    expect(s.days).toHaveLength(7);
    expect(s.days[6].key).toBe("2026-11-19");
    expect(s.week).toBe(3);
    expect(s.weekLogs).toHaveLength(2);
  });

  it("counts a streak ending today", () => {
    const s = weekStats([log("2026-11-19", "idle"), log("2026-11-18", "idle"), log("2026-11-17", "idle")], today);
    expect(s.streak).toBe(3);
  });

  it("keeps yesterday's streak alive before anything is logged today", () => {
    expect(weekStats([log("2026-11-18", "idle"), log("2026-11-17", "idle")], today).streak).toBe(2);
  });

  it("breaks the streak on a missed day", () => {
    expect(weekStats([log("2026-11-19", "idle"), log("2026-11-17", "idle")], today).streak).toBe(1);
    expect(weekStats([], today).streak).toBe(0);
  });
});

describe("challenges", () => {
  it("match on action kind, so they work in any language", () => {
    const carFree = CHALLENGES.find((c) => c.id === "car-free")!;
    const logs = [log("2026-11-19", "transit"), log("2026-11-19", "carpool"), log("2026-11-19", "energy")];
    expect(challengeProgress(carFree, logs)).toEqual({ count: 2, done: false, ratio: 2 / 3 });
    logs.push(log("2026-11-19", "active"), log("2026-11-19", "active"));
    expect(challengeProgress(carFree, logs)).toEqual({ count: 3, done: true, ratio: 1 });
  });

  it("understands logs saved before kinds existed", () => {
    expect(kindOf({ label: "🚇 Metro/bus instead of car (10 km)" })).toBe("transit");
    expect(kindOf({ label: "something custom" })).toBe("");
  });

  it("labels logs in the chosen language", () => {
    const l = { kind: "compost", label: "x" };
    expect(logLabel(l, "hi")).toContain("खाद");
    expect(logLabel(l, "en")).toContain("Composted");
  });
});

describe("quick actions", () => {
  it("use the same emission factors as the backend", () => {
    const transit = QUICK.find((q) => q.kind === "transit")!;
    expect(transit.kg).toBeCloseTo(10 * (2.31 / 15 - 0.03), 2);
    expect(new Set(QUICK.map((q) => q.kind)).size).toBe(QUICK.length);
  });
});
