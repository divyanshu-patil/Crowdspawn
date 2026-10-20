import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { LLMOnly, Plan } from "@repo/contracts";
import sample from "../public/sample-plan.json";
import { VersusLLM } from "../components/VersusLLM";

const llm = JSON.parse(readFileSync(resolve(process.cwd(), "public/sample-llm-only.json"), "utf8")) as LLMOnly;

describe("Qloo vs an LLM alone", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("loads the sample's static comparison and shows both lists, flagging names Qloo can't find", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify(llm)));
    vi.stubGlobal("fetch", fetch);
    render(<VersusLLM plan={sample as unknown as Plan} />);
    fireEvent.click(screen.getByTestId("vs-load"));
    const grid = await screen.findByTestId("vs-partners");
    expect(fetch).toHaveBeenCalledWith("/sample-llm-only.json");
    const first = llm.partners[0]!.picks[0]!;
    expect(within(grid).getByText(new RegExp(first.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))).toBeTruthy();
    const missing = llm.partners.flatMap((k) => k.picks).filter((p) => p.entity_id == null).length;
    expect(within(grid).queryAllByText("not in Qloo")).toHaveLength(missing);
    expect(screen.getByText(/never used in the plan/)).toBeTruthy();
  });
});
