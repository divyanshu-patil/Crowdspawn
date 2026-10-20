import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/" }));
const startAgent = vi.fn();
vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  api: { startAgent: (g: string) => startAgent(g) },
  streamAgent: vi.fn(),
}));

import { ApiError } from "../lib/api";
import { FrontDoor } from "../components/FrontDoor";
import { LaunchAgent } from "../components/LaunchAgent";
import { DRAFT_KEY } from "../components/NewPlanForm";

const GOAL = "A cozy farming game for PC. Where should I launch first?";

afterEach(() => {
  cleanup();
  push.mockReset();
  startAgent.mockReset();
});

describe("one front door (J16)", () => {
  it("the landing input starts the agent on /agent", () => {
    render(<FrontDoor />);
    fireEvent.change(screen.getByLabelText(/Describe your game/), { target: { value: GOAL } });
    fireEvent.click(screen.getByRole("button", { name: "Plan my launch" }));
    expect(push).toHaveBeenCalledWith(`/agent?goal=${encodeURIComponent(GOAL)}&run=1`);
    expect(screen.getByRole("link", { name: "Advanced: pick comps yourself" }).getAttribute("href")).toBe("/plan/new");
  });

  it("when the LLM is down, the description carries over to the form, which needs only Qloo", async () => {
    startAgent.mockRejectedValue(new ApiError("llm_unavailable", 502, "No LLM provider is configured"));
    window.history.pushState(null, "", `/agent?goal=${encodeURIComponent(GOAL)}&run=1`);
    render(<LaunchAgent />);
    await waitFor(() => expect(startAgent).toHaveBeenCalledWith(GOAL));
    expect(window.location.search).not.toContain("run=1"); // a reload doesn't start it again
    fireEvent.click(await screen.findByRole("button", { name: "Build the plan yourself" }));
    expect(JSON.parse(sessionStorage.getItem(DRAFT_KEY)!).draft.description).toBe(GOAL);
    expect(push).toHaveBeenCalledWith("/plan/new");
  });

  it("other failures show their message without the fallback", async () => {
    startAgent.mockRejectedValue(new ApiError("qloo_daily_cap", 503, "Today's live Qloo budget is used up."));
    window.history.pushState(null, "", `/agent?goal=${encodeURIComponent(GOAL)}&run=1`);
    render(<LaunchAgent />);
    expect(await screen.findByText("Today's live Qloo budget is used up.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Build the plan yourself" })).toBeNull();
  });
});
