import { describe, expect, it } from "vitest";
import type { Plan } from "@repo/contracts";
import sample from "../public/sample-delhi-plan.json"; // stable: the hero sample may be regenerated
import { planToMarkdown, rarity, skew } from "../lib/format";
import { initialProgress, reduce, xp } from "../lib/progress";
import { emptyDraft, isValid, toPlanIn, validateAll, validateComps, validateGame, validateRegions } from "../lib/validate";

const comp = (id: string) => ({ entity_id: id, name: id });

describe("form validation mirrors the API (F2)", () => {
  it("requires a title of at most 80 chars", () => {
    expect(validateGame(emptyDraft()).title).toBeTruthy();
    expect(validateGame({ ...emptyDraft(), title: "x".repeat(81) }).title).toBeTruthy();
    expect(validateGame({ ...emptyDraft(), title: "Moss Hollow" })).toEqual({});
  });
  it("caps description and tags", () => {
    expect(validateGame({ ...emptyDraft(), title: "a", description: "x".repeat(601) }).description).toBeTruthy();
    expect(validateGame({ ...emptyDraft(), title: "a", tags: Array(9).fill("t") }).tags).toBeTruthy();
  });
  it("needs 1-5 unique comps", () => {
    expect(validateComps(emptyDraft()).comps).toBeTruthy();
    expect(validateComps({ ...emptyDraft(), comps: ["a", "b", "c", "d", "e", "f"].map(comp) }).comps).toBeTruthy();
    expect(validateComps({ ...emptyDraft(), comps: [comp("a"), comp("a")] }).comps).toBeTruthy();
    expect(validateComps({ ...emptyDraft(), comps: [comp("a")] })).toEqual({});
  });
  it("needs 3-20 regions and a positive budget", () => {
    expect(validateRegions({ ...emptyDraft(), regions: ["a", "b"] }).regions).toBeTruthy();
    expect(validateRegions({ ...emptyDraft(), regions: Array.from({ length: 21 }, (_, i) => `r${i}`) }).regions).toBeTruthy();
    expect(validateRegions({ ...emptyDraft(), regions: ["a", "b", "c"], budget: "-5" }).budget).toBeTruthy();
    expect(validateRegions({ ...emptyDraft(), regions: ["a", "b", "c"], budget: "" })).toEqual({});
  });
  it("builds the PlanIn body", () => {
    const d = { ...emptyDraft(), title: " Moss ", comps: [comp("A")], regions: ["nyc", "lon", "tyo"], budget: "500" };
    expect(isValid(validateAll(d))).toBe(true);
    expect(toPlanIn(d)).toMatchObject({ game: { title: "Moss" }, comp_entity_ids: ["A"], budget_usd: 500, mode: "fast" });
    expect(toPlanIn(d)).toMatchObject({ culture_entity_ids: [], platforms: ["pc", "console", "mobile"] });
  });
  it("sends culture anchors and platforms, and needs at least one platform", () => {
    const d = { ...emptyDraft(), title: "Delhi Gullies", comps: [comp("A")], culture: [{ ...comp("G"), type: "urn:entity:movie" }] };
    expect(toPlanIn({ ...d, platforms: ["pc"] })).toMatchObject({ culture_entity_ids: ["G"], platforms: ["pc"] });
    expect(validateComps({ ...d, platforms: [] }).platforms).toBeTruthy();
    const six = Array.from({ length: 6 }, (_, i) => ({ ...comp(`c${i}`), type: "urn:entity:artist" }));
    expect(validateComps({ ...d, culture: six }).culture).toBeTruthy();
  });
});

describe("SSE progress reducer (F3)", () => {
  it("tracks steps, calls, warnings and completion", () => {
    let p = initialProgress();
    p = reduce(p, { id: 1, type: "queued", data: { plan_id: "x" } });
    p = reduce(p, { id: 2, type: "step_started", data: { step: "S1", label: "" } });
    p = reduce(p, { id: 3, type: "qloo_call", data: { result_id: "q1", step: "S1", endpoint: "/entities", cache_hit: false, duration_ms: 5, status: 200 } });
    p = reduce(p, { id: 4, type: "qloo_call", data: { result_id: "q2", step: "S2", endpoint: "/v2/insights", cache_hit: true, duration_ms: 1, status: 200 } });
    p = reduce(p, { id: 5, type: "step_done", data: { step: "S1", summary: "3 comps resolved" } });
    p = reduce(p, { id: 6, type: "warning", data: { code: "unresolved_comp", message: "m" } });
    expect(p.calls).toEqual({ live: 1, cached: 1 });
    expect(p.steps.S1).toEqual({ status: "done", summary: "3 comps resolved" });
    expect(p.warnings).toHaveLength(1);
    expect(xp(p)).toBeCloseTo(1 / 7);
    p = reduce(p, { id: 7, type: "done", data: { plan_id: "x" } });
    expect(p.status).toBe("done");
  });
  it("ignores replayed events after a reconnect", () => {
    let p = reduce(initialProgress(), { id: 3, type: "qloo_call", data: { result_id: "q1", step: "S1", endpoint: "/e", cache_hit: false, duration_ms: 1, status: 200 } });
    p = reduce(p, { id: 3, type: "qloo_call", data: { result_id: "q1", step: "S1", endpoint: "/e", cache_hit: false, duration_ms: 1, status: 200 } });
    expect(p.calls.live).toBe(1);
  });
  it("surfaces failures", () => {
    const p = reduce(initialProgress(), { id: 1, type: "failed", data: { code: "qloo_auth", message: "nope" } });
    expect(p.status).toBe("failed");
    expect(p.error?.code).toBe("qloo_auth");
  });
});

describe("formatting", () => {
  it("formats skews like the API facts", () => {
    expect(skew(0.185)).toBe("+18.5%");
    expect(skew(-0.09)).toBe("-9.0%");
  });
  it("assigns rarity tiers", () => {
    expect([rarity(0.951), rarity(0.948), rarity(0.8)]).toEqual(["legendary", "rare", "common"]);
  });
  it("exports the plan as Markdown with limits", () => {
    const plan = sample as unknown as Plan;
    const top = plan.cities[0]!;
    const md = planToMarkdown(plan);
    expect(md).toContain(
      `| 1 | ${top.name}, ${top.country} | ${top.score.toFixed(2)} | ${top.lift.toFixed(2)} | ${top.confidence} |`,
    );
    expect(md).toContain("Setting via: Gully Boy");
    expect(top.name).toBe("Mumbai"); // the sample is Delhi Gullies: culture fit puts India first
    expect(md).toContain("Affinity index, not a sales forecast.");
  });
});
