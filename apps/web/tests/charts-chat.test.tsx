import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { Plan } from "@repo/contracts";
import sample from "../public/sample-plan.json";
import { PlanCharts } from "../components/PlanCharts";
import { PlanChat } from "../components/PlanChat";

const plan = sample as unknown as Plan;

describe("analytics and ask this plan", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("charts every city in the scatter and the rank shift", () => {
    const { container } = render(<PlanCharts plan={plan} />);
    expect(screen.getByText("Why each city ranks")).toBeTruthy();
    expect(container.querySelectorAll(".slope")).toHaveLength(plan.cities.length);
    expect(container.querySelectorAll('[aria-label^="Scatter"] .dot')).toHaveLength(plan.cities.length);
  });

  it("sends the plan with the question and renders the cited answer", async () => {
    const top = plan.cities[0]!;
    const answer = `**${top.name}** leads [${top.result_ids[0]}].`;
    const fetch = vi.fn(async () => new Response(JSON.stringify({ answer, grounded: true, provider: "fake", model: "fake-1" })));
    vi.stubGlobal("fetch", fetch);
    render(<PlanChat plan={plan} traceHref="/sample/trace" />);
    fireEvent.click(screen.getByTestId("chat-open"));
    fireEvent.click(screen.getByText(`Why is ${top.name} the top spawn point?`));
    expect(await screen.findByText(top.name)).toBeTruthy();
    const body = JSON.parse((fetch.mock.calls[0] as unknown as [string, RequestInit])[1].body as string);
    expect(body.plan.id).toBe(plan.id);
  });
});
