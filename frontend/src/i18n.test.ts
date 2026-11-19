import { describe, expect, it } from "vitest";
import { fmtHour } from "./api";
import { dictionaries, translate } from "./i18n";

describe("i18n", () => {
  it("has a Hindi string for every English key", () => {
    for (const key of Object.keys(dictionaries.en)) {
      expect(dictionaries.hi[key as keyof typeof dictionaries.en], key).toBeTruthy();
    }
  });
  it("translates", () => {
    expect(translate("hi", "tab_today")).toBe("आज");
    expect(translate("en", "tab_today")).toBe("Today");
  });
});

describe("fmtHour", () => {
  it.each([["2026-11-19T00:00", "12 AM"], ["2026-11-19T07:00", "7 AM"], ["2026-11-19T12:00", "12 PM"], ["2026-11-19T19:00", "7 PM"]])(
    "%s → %s", (iso, out) => expect(fmtHour(iso)).toBe(out));
  it("handles missing", () => expect(fmtHour(null)).toBe("—"));
});
