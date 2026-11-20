import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, errorMessage, fmtHour, LEVEL_COLORS, levelInk, query } from "./api";

/** WCAG 2.x relative luminance and contrast ratio. */
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

function mockFetch(impl: (url: string, init?: RequestInit) => Promise<Response>) {
  const fn = vi.fn(impl);
  vi.stubGlobal("fetch", fn);
  return fn;
}
const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

afterEach(() => { vi.unstubAllGlobals(); });

describe("errorMessage", () => {
  it("uses the first validation error's field name", () => {
    expect(errorMessage({ detail: [{ loc: ["body", "lat"], msg: "too big" }, { msg: "ignored" }] }, 422)).toBe("lat: too big");
  });
  it("falls back to 'Input' when a validation error has no location", () => {
    expect(errorMessage({ detail: [{ msg: "bad value" }] }, 422)).toBe("Input: bad value");
  });
  it("ignores unknown shapes", () => {
    expect(errorMessage({ detail: 42 }, 500)).toMatch(/Something went wrong/);
    expect(errorMessage("oops", 503)).toMatch(/Something went wrong/);
    expect(errorMessage({ detail: [] }, 429)).toMatch(/Too many requests/);
  });
});

describe("request transport", () => {
  it("returns the parsed body on success and sends coordinates in the query", async () => {
    const fetchFn = mockFetch(() => json({ reports: [] }));
    await expect(api.reports({ name: "Delhi", lat: 28.61, lon: 77.21 })).resolves.toEqual({ reports: [] });
    expect(fetchFn).toHaveBeenCalledWith("/api/reports?lat=28.61&lon=77.21", undefined);
  });

  it("posts JSON bodies with the right content type", async () => {
    const fetchFn = mockFetch(() => json({ distance_km: 5, occupants: 2, rows: [], exposure_note: "" }));
    await api.mobility(5, 2);
    const [url, init] = fetchFn.mock.calls[0];
    expect(url).toBe("/api/mobility");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init?.body))).toEqual({ distance_km: 5, occupants: 2 });
  });

  it("sends the household's commute mode with the routine request", async () => {
    const fetchFn = mockFetch(() => json({ steps: [] }));
    const household = {
      members: [
        { name: "A", age_group: "adult" as const, conditions: [], outdoor_hours: 1, exercises_outdoors: false, commute_mode: null },
        { name: "B", age_group: "adult" as const, conditions: [], outdoor_hours: 1, exercises_outdoors: false, commute_mode: "metro" as const },
      ],
      home: { has_purifier: false, cooking_fuel: "lpg" as const, smoker_at_home: false, burns_incense: false, has_pets: false },
    };
    await api.routine({ name: "X", lat: 1, lon: 2 }, household, "en");
    expect(JSON.parse(String(fetchFn.mock.calls[0][1]?.body)).commute_mode).toBe("metro");
  });

  it("raises ApiError with the server's message and status", async () => {
    mockFetch(() => json({ detail: "Report not found" }, 404));
    const err = await api.confirmReport(7).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ message: "Report not found", status: 404, name: "ApiError" });
  });

  it("copes with a non-JSON error body", async () => {
    mockFetch(() => Promise.resolve(new Response("<html>Bad gateway</html>", { status: 502 })));
    await expect(api.health()).rejects.toMatchObject({ status: 502, message: expect.stringMatching(/Something went wrong/) });
  });

  it("reports network failures as offline (status 0)", async () => {
    mockFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(api.air({ name: "X", lat: 1, lon: 2 })).rejects.toMatchObject({ status: 0, message: "You seem to be offline." });
  });

  it("uploads photos as multipart form data", async () => {
    const fetchFn = mockFetch(() => json({ category: "other" }));
    await api.analyzePhoto(new File(["x"], "smoke.jpg", { type: "image/jpeg" }), "hi");
    const body = fetchFn.mock.calls[0][1]?.body as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("lang")).toBe("hi");
    expect((body.get("photo") as File).name).toBe("smoke.jpg");
  });
});

describe("display helpers", () => {
  it("builds encoded query strings", () => {
    expect(query({ q: "New Delhi & NCR", lang: "en" })).toBe("q=New+Delhi+%26+NCR&lang=en");
  });

  it("formats hours on a 12-hour clock", () => {
    expect(fmtHour("2026-11-19T13:00")).toBe("1 PM");
    expect(fmtHour(undefined)).toBe("—");
  });

  it("picks a text colour with WCAG AA contrast on every AQI level colour", () => {
    LEVEL_COLORS.forEach((bg, level) => {
      expect(contrast(bg, levelInk(level)), `level ${level} (${bg})`).toBeGreaterThanOrEqual(4.5);
    });
    expect(levelInk(null)).toBe(levelInk(0));
  });
});
