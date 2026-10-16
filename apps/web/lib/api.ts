import type {
  ActivityOut,
  EntityOut,
  PlaceHit,
  ScoutArea,
  ScoutFit,
  Health,
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("api_unreachable", 0, `Can't reach the Crowdspawn API at ${API_URL}. Is it running?`);
  }
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
  places: (q: string) => request<PlaceHit[]>(`/v1/scout/places?q=${encodeURIComponent(q)}`),
  activity: () => request<ActivityOut>("/v1/scout/activity"),
  area: (lat: number, lon: number) =>
    request<ScoutArea>("/v1/scout/area", { method: "POST", body: JSON.stringify({ lat, lon }) }),
  fit: (lat: number, lon: number, comp_entity_ids: string[], platforms: string[]) =>
    request<ScoutFit>("/v1/scout/fit", {
      method: "POST",
      body: JSON.stringify({ lat, lon, comp_entity_ids, platforms }),
    }),
  trace: (id: string) => request<TraceRow[]>(`/v1/plans/${id}/trace`),
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
