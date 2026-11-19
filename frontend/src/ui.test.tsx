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
