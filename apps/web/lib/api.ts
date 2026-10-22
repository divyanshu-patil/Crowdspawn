import type {
  ActivityOut,
  AgentEvent,
  AgentRun,
  AskOut,
  EntityOut,
  GenreHeat,
  PlatformMix,
  PlaceHit,
  ScoutArea,
  ScoutFit,
  ScoutJudge,
  Health,
  LLMOnly,
  Plan,
  PlanCreated,
  PlanEvent,
  PlanIn,
  Problem,
  Region,
  SuggestOut,
  TraceRow,
} from "@repo/contracts";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public code: string,
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** "waking": a request has waited over SLOW_MS (a sleeping free host takes 30-60 s); "down": one failed to connect. */
export type ServerState = "ok" | "waking" | "down";
export const SLOW_MS = 3000;
const listeners = new Set<(s: ServerState) => void>();
let serverState: ServerState = "ok";
let slowPending = 0;

function setServerState(s: ServerState) {
  serverState = s;
  listeners.forEach((f) => f(s));
}

export function onServerState(fn: (s: ServerState) => void): () => void {
  listeners.add(fn);
  fn(serverState);
  return () => listeners.delete(fn);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  let slow = false;
  const timer = setTimeout(() => {
    slow = true;
    slowPending++;
    setServerState("waking");
  }, SLOW_MS);
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
    });
  } catch {
    setServerState("down");
    throw new ApiError("api_unreachable", 0, `Can't reach the Crowdspawn API at ${API_URL}. It may be starting up: try again in a minute.`);
  } finally {
    clearTimeout(timer);
    if (slow) slowPending--;
  }
  if (serverState !== "ok" && slowPending === 0) setServerState("ok");
  if (!res.ok) {
    const p = (await res.json().catch(() => null)) as Problem | null;
    throw new ApiError(p?.code ?? "http_error", res.status, p?.detail ?? `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  regions: () => request<Region[]>("/v1/regions"),
  search: (q: string) => request<EntityOut[]>(`/v1/entities/search?q=${encodeURIComponent(q)}&type=videogame`),
  suggest: (game: { title: string; description: string; tags: string[] }) =>
    request<SuggestOut>("/v1/comps/suggest", { method: "POST", body: JSON.stringify(game) }),
  searchCulture: (q: string) => request<EntityOut[]>(`/v1/entities/search?q=${encodeURIComponent(q)}&type=culture`),
  suggestCulture: (game: { title: string; description: string; tags: string[] }) =>
    request<SuggestOut>("/v1/culture/suggest", { method: "POST", body: JSON.stringify(game) }),
  createPlan: (body: PlanIn) => request<PlanCreated>("/v1/plans", { method: "POST", body: JSON.stringify(body) }),
  plan: (id: string) => request<Plan>(`/v1/plans/${id}`),
  startAgent: (goal: string) =>
    request<PlanCreated>("/v1/agent", { method: "POST", body: JSON.stringify({ goal }) }),
  agent: (id: string) => request<AgentRun>(`/v1/agent/${id}`),
  places: (q: string) => request<PlaceHit[]>(`/v1/scout/places?q=${encodeURIComponent(q)}`),
  activity: () => request<ActivityOut>("/v1/scout/activity"),
  area: (lat: number, lon: number) =>
    request<ScoutArea>("/v1/scout/area", { method: "POST", body: JSON.stringify({ lat, lon }) }),
  judge: (body: {
    lat: number;
    lon: number;
    title: string;
    description: string;
    platforms: string[];
    comp_entity_ids: string[];
  }) => request<ScoutJudge>("/v1/scout/judge", { method: "POST", body: JSON.stringify(body) }),
  fit: (lat: number, lon: number, comp_entity_ids: string[], platforms: string[]) =>
    request<ScoutFit>("/v1/scout/fit", {
      method: "POST",
      body: JSON.stringify({ lat, lon, comp_entity_ids, platforms }),
    }),
  trace: (id: string) => request<TraceRow[]>(`/v1/plans/${id}/trace`),
  ask: (plan: Plan, question: string) =>
    request<AskOut>("/v1/ask", { method: "POST", body: JSON.stringify({ plan, question }) }),
  askScout: (body: { place: string; mix: PlatformMix; genres: GenreHeat[]; games: string[]; judge: ScoutJudge | null; question: string }) =>
    request<AskOut>("/v1/scout/ask", { method: "POST", body: JSON.stringify(body) }),
  llmOnly: (id: string) => request<LLMOnly>(`/v1/plans/${id}/llm-only`, { method: "POST" }),
};

const EVENT_TYPES: PlanEvent["type"][] = [
  "queued",
  "step_started",
  "step_done",
  "qloo_call",
  "warning",
  "done",
  "failed",
];

const AGENT_EVENTS: AgentEvent["type"][] = ["queued", "step", "observation", "qloo_call", "answer", "done", "failed"];

/** Follow an agent run's steps live (same SSE replay and resume as plans). */
export function streamAgent(
  id: string,
  onEvent: (ev: AgentEvent & { id: number }) => void,
  onConnection: (state: "open" | "retrying") => void,
): () => void {
  const es = new EventSource(`${API_URL}/v1/agent/${id}/stream`);
  for (const type of AGENT_EVENTS) {
    es.addEventListener(type, (e) => {
      const msg = e as MessageEvent<string>;
      onEvent({ type, data: JSON.parse(msg.data), id: Number(msg.lastEventId) } as AgentEvent & { id: number });
      if (type === "done" || type === "failed") es.close();
    });
  }
  es.onopen = () => onConnection("open");
  es.onerror = () => {
    if (es.readyState !== EventSource.CLOSED) onConnection("retrying");
  };
  return () => es.close();
}

/**
 * Subscribe to a plan's SSE stream. EventSource reconnects on its own and sends
 * Last-Event-ID, so the server resumes where we left off. Returns an unsubscribe function.
 */
export function streamPlan(
  id: string,
  onEvent: (ev: PlanEvent & { id: number }) => void,
  onConnection: (state: "open" | "retrying") => void,
): () => void {
  const es = new EventSource(`${API_URL}/v1/plans/${id}/stream`);
  for (const type of EVENT_TYPES) {
    es.addEventListener(type, (e) => {
      const msg = e as MessageEvent<string>;
      onEvent({ type, data: JSON.parse(msg.data), id: Number(msg.lastEventId) } as PlanEvent & { id: number });
      if (type === "done" || type === "failed") es.close();
    });
  }
  es.onopen = () => onConnection("open");
  es.onerror = () => {
    if (es.readyState !== EventSource.CLOSED) onConnection("retrying");
  };
  return () => es.close();
}
