import type { Plan } from "@repo/contracts";

/** Plans this browser has opened. Per-viewer convenience only: plans live on the server. */
export type RecentPlan = { id: string; title: string; status: Plan["status"]; created_at: string; top?: string; cities: number };

const KEY = "crowdspawn:recent";
const MAX = 30;

export function recentPlans(): RecentPlan[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]") as unknown;
    return Array.isArray(v) ? (v as RecentPlan[]) : [];
  } catch {
    return [];
  }
}

function save(list: RecentPlan[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX)));
  } catch {
    // private window or storage blocked: the list just stays empty
  }
}

export function rememberPlan(p: Plan) {
  const entry: RecentPlan = {
    id: p.id,
    title: p.input.game.title,
    status: p.status,
    created_at: p.created_at,
    top: p.cities[0]?.name,
    cities: p.cities.length,
  };
  save([entry, ...recentPlans().filter((r) => r.id !== p.id)]);
}

export function forgetPlan(id: string) {
  save(recentPlans().filter((r) => r.id !== id));
}
