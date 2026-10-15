import type { PlanEvent, Warning } from "@repo/contracts";

export const STEPS: { key: string; label: string; quest: string }[] = [
  { key: "S1", label: "Resolve comps", quest: "Identify your rivals" },
  { key: "S2", label: "Expand comp set", quest: "Scout the genre" },
  { key: "S3", label: "Score cities vs baseline", quest: "Find the spawn points" },
  { key: "S4", label: "Read the audience", quest: "Read the party" },
  { key: "S5", label: "Find partners", quest: "Gather allies" },
  { key: "S6", label: "Gap view", quest: "Map the gap" },
  { key: "S7", label: "Split the budget", quest: "Spend the gold" },
  { key: "S8", label: "Write the brief", quest: "Write the battle plan" },
];

export type StepState = { status: "pending" | "active" | "done"; summary?: string };

export type Progress = {
  status: "connecting" | "running" | "done" | "failed";
  steps: Record<string, StepState>;
  calls: { live: number; cached: number };
  lastCall?: { result_id: string; endpoint: string; cache_hit: boolean };
  warnings: Warning[];
  error?: { code: string; message: string };
  lastId: number;
  hasGap: boolean;
};

export const initialProgress = (): Progress => ({
  status: "connecting",
  steps: Object.fromEntries(STEPS.map((s) => [s.key, { status: "pending" }])),
  calls: { live: 0, cached: 0 },
  warnings: [],
  lastId: 0,
  hasGap: false,
});

/** Pure reducer over SSE events. Replays are idempotent: events at or below lastId are ignored. */
export function reduce(p: Progress, ev: PlanEvent & { id: number }): Progress {
  if (ev.id && ev.id <= p.lastId) return p;
  const next: Progress = { ...p, lastId: ev.id || p.lastId };
  switch (ev.type) {
    case "queued":
      return { ...next, status: "running" };
    case "step_started":
      return {
        ...next,
        status: "running",
        hasGap: p.hasGap || ev.data.step === "S6",
        steps: { ...p.steps, [ev.data.step]: { status: "active" } },
      };
    case "step_done":
      return { ...next, steps: { ...p.steps, [ev.data.step]: { status: "done", summary: ev.data.summary } } };
    case "qloo_call":
      return {
        ...next,
        calls: {
          live: p.calls.live + (ev.data.cache_hit ? 0 : 1),
          cached: p.calls.cached + (ev.data.cache_hit ? 1 : 0),
        },
        lastCall: { result_id: ev.data.result_id, endpoint: ev.data.endpoint, cache_hit: ev.data.cache_hit },
      };
    case "warning":
      return { ...next, warnings: [...p.warnings, ev.data] };
    case "done":
      return { ...next, status: "done" };
    case "failed":
      return { ...next, status: "failed", error: ev.data };
  }
}

/** 0..1 completion for the XP bar. S6 only counts when the plan has a gap step. */
export function xp(p: Progress): number {
  const keys = STEPS.map((s) => s.key).filter((k) => k !== "S6" || p.hasGap);
  const done = keys.filter((k) => p.steps[k]?.status === "done").length;
  const active = keys.some((k) => p.steps[k]?.status === "active") ? 0.5 : 0;
  return Math.min(1, (done + active) / keys.length);
}
