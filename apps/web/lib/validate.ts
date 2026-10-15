// Mirrors the API's PlanIn validation (apps/api/src/crowdspawn_api/schemas.py).

export const LIMITS = {
  titleMax: 80,
  descriptionMax: 600,
  tagsMax: 8,
  compsMin: 1,
  compsMax: 5,
  regionsMin: 3,
  regionsMax: 15,
  budgetMax: 10_000_000,
};

export type Draft = {
  title: string;
  description: string;
  tags: string[];
  comps: { entity_id: string; name: string; image_url?: string | null; year?: number | null }[];
  regions: string[];
  budget: string;
  previous: { entity_id: string; name: string }[];
};

export const emptyDraft = (): Draft => ({
  title: "",
  description: "",
  tags: [],
  comps: [],
  regions: [],
  budget: "",
  previous: [],
});

export type Errors = Partial<Record<"title" | "description" | "tags" | "comps" | "regions" | "budget", string>>;

export function validateGame(d: Draft): Errors {
  const e: Errors = {};
  const title = d.title.trim();
  if (!title) e.title = "Give your game a title.";
  else if (title.length > LIMITS.titleMax) e.title = `Keep the title under ${LIMITS.titleMax} characters.`;
  if (d.description.length > LIMITS.descriptionMax)
    e.description = `Keep the description under ${LIMITS.descriptionMax} characters.`;
  if (d.tags.length > LIMITS.tagsMax) e.tags = `Use at most ${LIMITS.tagsMax} tags.`;
  return e;
}

export function validateComps(d: Draft): Errors {
  const ids = d.comps.map((c) => c.entity_id);
  if (ids.length < LIMITS.compsMin) return { comps: "Pick at least one comparable game." };
  if (ids.length > LIMITS.compsMax) return { comps: `Pick at most ${LIMITS.compsMax} comparable games.` };
  if (new Set(ids).size !== ids.length) return { comps: "Each comparable game can only be picked once." };
  return {};
}

export function validateRegions(d: Draft): Errors {
  const e: Errors = {};
  if (d.regions.length < LIMITS.regionsMin) e.regions = `Pick at least ${LIMITS.regionsMin} cities.`;
  else if (d.regions.length > LIMITS.regionsMax) e.regions = `Pick at most ${LIMITS.regionsMax} cities.`;
  if (d.budget.trim()) {
    const n = Number(d.budget);
    if (!Number.isFinite(n) || n <= 0) e.budget = "Budget must be a positive number of dollars.";
    else if (n > LIMITS.budgetMax) e.budget = "That budget is above what the planner accepts.";
  }
  return e;
}

export const validateAll = (d: Draft): Errors => ({ ...validateGame(d), ...validateComps(d), ...validateRegions(d) });

export const isValid = (e: Errors) => Object.keys(e).length === 0;

export function toPlanIn(d: Draft) {
  return {
    game: { title: d.title.trim(), description: d.description.trim(), tags: d.tags },
    comp_entity_ids: d.comps.map((c) => c.entity_id),
    regions: d.regions,
    budget_usd: d.budget.trim() ? Number(d.budget) : null,
    previous_game_entity_ids: d.previous.map((p) => p.entity_id),
    mode: "fast" as const,
  };
}
