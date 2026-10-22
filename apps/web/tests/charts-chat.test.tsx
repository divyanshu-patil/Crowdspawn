import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { Plan } from "@repo/contracts";
import sample from "../public/sample-plan.json";
import { PlanCharts } from "../components/PlanCharts";
import { PlanChat } from "../components/PlanChat";
import { forgetPlan, recentPlans, rememberPlan } from "../lib/recent";

const plan = sample as unknown as Plan;

describe("analytics and ask this plan", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("explains the plan in plain charts with a takeaway each", () => {
    const { container } = render(<PlanCharts plan={plan} />);
    expect(screen.getByText("What makes each city a good fit")).toBeTruthy();
    expect(container.querySelectorAll(".factors-row")).toHaveLength(Math.min(6, plan.cities.length));
    expect(screen.getByText("Launch here")).toBeTruthy();
    expect(container.querySelectorAll(".takeaway").length).toBeGreaterThanOrEqual(3);
  });

  it("remembers opened plans, newest first, without duplicates", () => {
    rememberPlan(plan);
    rememberPlan({ ...plan, id: "other" });
    rememberPlan(plan);
    expect(recentPlans().map((r) => r.id)).toEqual([plan.id, "other"]);
    forgetPlan("other");
    expect(recentPlans()).toHaveLength(1);
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
