// Friendly aliases over the generated OpenAPI types. Regenerate with `pnpm --filter @repo/contracts generate`.
import type { components } from "./openapi";

type S = components["schemas"];

export type Plan = S["Plan"];
export type PlanIn = S["PlanIn"];
export type PlanCreated = S["PlanCreated"];
export type City = S["City"];
export type Partner = S["Partner"];
export type Partners = S["Partners"];
export type ExpandedGame = S["ExpandedGame"];
export type Audience = S["Audience"];
export type Brief = S["Brief"];
export type Gap = S["Gap"];
export type Region = S["Region"];
export type EntityOut = S["EntityOut"];
export type SuggestOut = S["SuggestOut"];
export type TraceRow = S["TraceRow"];
export type Health = S["Health"];
export type Warning = S["Warning_"];
export type CultureAnchor = S["CultureAnchor"];
export type PlaceHit = S["PlaceHit"];
export type PlatformMix = S["PlatformMix"];
export type AreaActivity = S["AreaActivity"];
export type ActivityOut = S["ActivityOut"];
export type ScoutArea = S["ScoutArea"];
export type ScoutFit = S["ScoutFit"];
export type GenreHeat = S["GenreHeat"];
export type LocalGame = S["LocalGame"];
export type ScoutJudge = S["ScoutJudge"];
export type RankedPlace = S["RankedPlace"];
export type AgentRun = S["AgentRun"];
export type AgentStep = S["AgentStepOut"];
export type PlanDraft = S["PlanDraft"];

export type AgentEvent =
  | { type: "queued"; data: { id: string } }
  | { type: "step"; data: { n: number; thought: string; tool: string; args: Record<string, unknown> } }
  | { type: "observation"; data: { n: number; text: string; ok: boolean } }
  | { type: "qloo_call"; data: { cache_hit: boolean; endpoint: string } }
  | { type: "answer"; data: { answer: string; source: "llm" | "template" } }
  | { type: "done"; data: { id: string } }
  | { type: "failed"; data: { code: string; message: string } };
export type Confidence = City["confidence"];
export type PartnerType = keyof Partners;

export type Problem = { type: string; title: string; status: number; detail: string; code: string };

export type PlanEvent =
  | { type: "queued"; data: { plan_id: string } }
  | { type: "step_started"; data: { step: string; label: string } }
  | { type: "step_done"; data: { step: string; summary: string } }
  | {
      type: "qloo_call";
      data: { result_id: string; step: string; endpoint: string; cache_hit: boolean; duration_ms: number; status: number };
    }
  | { type: "warning"; data: { code: string; message: string } }
  | { type: "done"; data: { plan_id: string } }
  | { type: "failed"; data: { code: string; message: string } };
