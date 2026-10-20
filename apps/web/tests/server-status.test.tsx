import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { api, SLOW_MS } from "../lib/api";
import { ServerStatus } from "../components/ServerStatus";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("waking the server (J9)", () => {
  it("says the server is starting when a request is slow, and clears when it answers", async () => {
    vi.useFakeTimers();
    let answer: (r: Response) => void = () => {};
    vi.stubGlobal("fetch", () => new Promise<Response>((r) => (answer = r)));
    render(<ServerStatus />);
    const pending = api.health();
    expect(screen.queryByText(/Starting the server/)).toBeNull();
    await act(async () => void vi.advanceTimersByTime(SLOW_MS + 1));
    expect(screen.getByText("Starting the server, this can take up to a minute…")).toBeTruthy();
    await act(async () => {
      answer(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
      await pending;
    });
    expect(screen.queryByText(/Starting the server/)).toBeNull();
  });

  it("offers a retry and the sample when the server can't be reached", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new TypeError("Failed to fetch")));
    render(<ServerStatus />);
    await act(async () => {
      await api.health().catch(() => {});
    });
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "See the sample plan" }).getAttribute("href")).toBe("/sample");
    vi.stubGlobal("fetch", () => Promise.resolve(new Response("{}", { status: 200 })));
    await act(async () => void (await api.health())); // leave the shared state "ok" for other tests
  });
});
