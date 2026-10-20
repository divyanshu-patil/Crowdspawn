import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { AUDIENCE, AccuracyReport, AccuracySummary, EVAL, SampleCallout } from "../components/Accuracy";

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

  it("the sample's callout states this game's evaluation facts from the same JSON (J19)", () => {
    const row = EVAL.tuning.scenarios.find((r) => r.game.startsWith("Long Haul:"))!;
    const { container } = render(<SampleCallout game="Long Haul" />);
    const text = container.textContent!;
    const name = (a2: string) => new Intl.DisplayNames(["en"], { type: "region" }).of(a2)!;
    expect(text).toContain(`Google Trends puts ${name(row.truth_top3[0]!)} first for ${row.truth}`);
    expect(text).toContain(`Crowdspawn's #1 city was ${row.crowdspawn_city}`);
    expect(text).toContain(`put ${name(row.llm_top3[0]!)} first`);
    expect(text).toContain("designed on");
    cleanup();
    expect(render(<SampleCallout game="Not in the evaluation" />).container.textContent).toBe("");
  });

  it("the audience check in the app and the README quote the same numbers", () => {
    const { getByTestId } = render(<AccuracyReport />);
    const rows = getByTestId("audience-check").querySelectorAll("tbody tr");
    expect(rows).toHaveLength(AUDIENCE.rows.length);
    const readme = readFileSync(resolve(process.cwd(), "../../README.md"), "utf8");
    expect(readme).toContain(`ρ ${AUDIENCE.rho_qloo}`);
    expect(readme).toContain(`ρ ${AUDIENCE.rho_llm}`);
  });
});
