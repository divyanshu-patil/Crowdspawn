import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { AccuracySummary, EVAL } from "../components/Accuracy";

describe("accuracy evidence (J15)", () => {
  it("renders the held-out numbers straight from the evaluation JSON", () => {
    render(<AccuracySummary />);
    const box = within(screen.getByTestId("accuracy-numbers"));
    for (const m of EVAL.holdout.methods) {
      const stat = box.getByText(m.method).closest(".stat")!;
      expect(stat.textContent).toBe(`${m.method}${m.top1} of ${m.n}top 3: ${m.top3} of ${m.n}`);
    }
    cleanup();
  });

  it("the README quotes the same held-out numbers", () => {
    const readme = readFileSync(resolve(process.cwd(), "../../README.md"), "utf8"); // vitest runs in apps/web
    for (const m of EVAL.holdout.methods)
      expect(readme).toContain(`| ${m.method} | ${m.top1} of ${m.n} | ${m.top3} of ${m.n} | ${m.rho} |`);
  });
});
