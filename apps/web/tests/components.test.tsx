import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
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
  it("turns agent step citations into chips that point at the step (J24)", () => {
    const onStep = vi.fn();
    render(<RichText text="Launch in **Tokyo** [s3, s5]." traceHref="#" onStep={onStep} />);
    fireEvent.click(screen.getByRole("button", { name: "Show step 5" }));
    expect(onStep).toHaveBeenCalledWith(5);
    expect(screen.getByRole("button", { name: "Show step 3" }).textContent).toBe("s3");
  });
});
