import { afterEach, describe, expect, it, vi } from "vitest";
import type { GridCell } from "./api";
import { speechRecognition } from "./Chat";
import { prefersReducedMotion, scrollBehavior } from "./motion";
import { cleanDescription } from "./pages/Community";
import { modeLabel } from "./pages/Family";
import { northUp } from "./pages/Today";

afterEach(() => { vi.unstubAllGlobals(); });

const stubMotion = (reduce: boolean) =>
  vi.stubGlobal("window", { matchMedia: (q: string) => ({ matches: reduce && q.includes("reduce") }) });

describe("reduced motion", () => {
  it("scrolls smoothly by default", () => {
    stubMotion(false);
    expect(prefersReducedMotion()).toBe(false);
    expect(scrollBehavior()).toBe("smooth");
  });
  it("jumps instantly when the user asks for less motion", () => {
    stubMotion(true);
    expect(prefersReducedMotion()).toBe(true);
    expect(scrollBehavior()).toBe("auto");
  });
  it("is safe outside a browser", () => {
    expect(prefersReducedMotion()).toBe(false);
  });
});

describe("area grid orientation", () => {
  it("draws the northern row first, keeping west→east order within rows", () => {
    // The API returns south→north rows; cell value = row * 10 + column.
    const cells = Array.from({ length: 25 }, (_, i): GridCell =>
      ({ lat: Math.floor(i / 5), lon: i % 5, pm2_5: Math.floor(i / 5) * 10 + (i % 5), pm10: null, level: 0, color: "#000" }));
    const drawn = northUp(cells).map((c) => c.pm2_5);
    expect(drawn.slice(0, 5)).toEqual([40, 41, 42, 43, 44]);
    expect(drawn.slice(-5)).toEqual([0, 1, 2, 3, 4]);
    expect(drawn[12]).toBe(22); // the centre cell (the user's location) stays in the middle
  });
});

describe("community report text", () => {
  it("removes links and markup and trims to the 500-character limit", () => {
    expect(cleanDescription("Smoke at <b>gate</b> see https://x.io/a and www.y.com now")).toBe("Smoke at gate see  and  now");
    expect(cleanDescription("a".repeat(600))).toHaveLength(500);
  });
});

describe("travel mode labels", () => {
  it("translates known modes and passes unknown ones through", () => {
    expect(modeLabel("metro", "en")).toBe("🚇 Metro");
    expect(modeLabel("metro", "hi")).toBe("🚇 मेट्रो");
    expect(modeLabel("hovercraft", "en")).toBe("hovercraft");
  });
});

describe("voice input detection", () => {
  it("prefers the standard API, falls back to the WebKit prefix, and is undefined when missing", () => {
    class Std {}
    class Webkit {}
    expect(speechRecognition({ SpeechRecognition: Std, webkitSpeechRecognition: Webkit } as never)).toBe(Std);
    expect(speechRecognition({ webkitSpeechRecognition: Webkit } as never)).toBe(Webkit);
    expect(speechRecognition({} as never)).toBeUndefined();
  });
});
