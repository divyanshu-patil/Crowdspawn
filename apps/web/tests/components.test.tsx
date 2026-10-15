import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfidenceBadge, RichText } from "../components/ui";

describe("components", () => {
  it("confidence uses text, not only colour (F7)", () => {
    render(<ConfidenceBadge level="medium" />);
    expect(screen.getByText("medium")).toBeTruthy();
  });
  it("turns citations into trace links and bold names into highlights (F5)", () => {
    const { container } = render(<RichText text="**Tokyo** leads [q21, q22]." traceHref="/plan/x/trace" />);
    const links = [...container.querySelectorAll("a.cite")].map((a) => a.getAttribute("href"));
    expect(links).toEqual(["/plan/x/trace#q21", "/plan/x/trace#q22"]);
    expect(container.querySelector("strong")?.textContent).toBe("Tokyo");
  });
});
