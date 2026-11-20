import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { errorMessage } from "./api";
import { Markdown } from "./Chat";

describe("errorMessage", () => {
  it("passes through plain FastAPI messages", () => {
    expect(errorMessage({ detail: "Report not found" }, 404)).toBe("Report not found");
  });
  it("turns validation lists into a readable field message", () => {
    const body = { detail: [{ loc: ["body", "distance_km"], msg: "Input should be less than or equal to 500" }] };
    expect(errorMessage(body, 422)).toBe("distance_km: Input should be less than or equal to 500");
  });
  it("has friendly fallbacks", () => {
    expect(errorMessage({}, 429)).toMatch(/Too many requests/);
    expect(errorMessage(null, 500)).toMatch(/Something went wrong/);
  });
});

describe("chat Markdown", () => {
  it("renders bold text and bullet lists", () => {
    const html = renderToStaticMarkup(<Markdown text={"**Tip:** stay in\n* close windows\n- run purifier"} />);
    expect(html).toContain("<strong>Tip:</strong>");
    expect(html.match(/<li>/g)).toHaveLength(2);
  });
  it("never injects HTML from the model (no XSS)", () => {
    const html = renderToStaticMarkup(<Markdown text={'<img src=x onerror="alert(1)"> **<script>x</script>**'} />);
    expect(html).not.toContain("<img");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });
});

describe("Today helpers", async () => {
  const { usAqiText, cityTimeAhead } = await import("./pages/Today");

  it("shows US AQI 0 as 0, and only missing values as a dash", () => {
    expect(usAqiText(0)).toBe("0");
    expect(usAqiText(152.6)).toBe("153");
    expect(usAqiText(null)).toBe("—");
    expect(usAqiText(Number.NaN)).toBe("—");
  });

  it("defaults the Guardian time from the city's own forecast clock", () => {
    const hourly = Array.from({ length: 6 }, (_, i) => ({ time: `2026-11-19T${String(14 + i).padStart(2, "0")}:00`, pm2_5: 1, pm10: 1, level: 0, us_aqi: 1 }));
    const snap = { hourly, now_index: 1 } as never;
    expect(cityTimeAhead(snap, 3)).toBe("2026-11-19T18:00");
    expect(cityTimeAhead(snap, 99)).toBe("2026-11-19T19:00"); // clamps to the last forecast hour
  });
});

describe("accessible components", async () => {
  const { AppProvider } = await import("./store");
  const { ActionList, Btn, Card } = await import("./components");
  const render = (node: React.ReactNode) => renderToStaticMarkup(<AppProvider>{node}</AppProvider>);

  it("announces a busy button and keeps it from being pressed twice", () => {
    const html = render(<Btn busy>Save</Btn>);
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("disabled");
    expect(html).toContain('role="status"');
    expect(html).toContain("Please wait…");
    expect(html).not.toContain("Save");
  });

  it("is a plain button (never an accidental form submit) when idle", () => {
    const html = render(<Btn>Save</Btn>);
    expect(html).toContain('type="button"');
    expect(html).not.toContain("aria-busy");
  });

  it("hides decorative card icons from screen readers", () => {
    const html = render(<Card title="Pollutants" icon="🧪">x</Card>);
    expect(html).toMatch(/<h3><span aria-hidden="true">🧪<\/span>Pollutants<\/h3>/);
  });

  it("keeps the reason behind every action one click away", () => {
    const html = render(<ActionList items={[{ text: "Close windows", why: "Outdoor air is worse", priority: "high" }]} />);
    expect(html).toContain('<div class="ico" aria-hidden="true">⚠️</div>');
    expect(html).toContain("<summary>Why?</summary>");
    expect(html).toContain("Outdoor air is worse");
  });
});
