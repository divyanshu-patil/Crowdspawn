import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/" }));

import { STEPS, Tour } from "../components/Tour";

describe("tour", () => {
  it("opens from the nav, advances, and moves to the next step's page", () => {
    render(<Tour />);
    fireEvent.click(screen.getByRole("button", { name: "Tour" }));
    expect(screen.getByText(`Step 1 / ${STEPS.length}`)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText(STEPS[1]!.title)).toBeTruthy();
    expect(push).not.toHaveBeenCalled(); // step 2 is on the same page
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(push).toHaveBeenCalledWith("/sample");
    fireEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
