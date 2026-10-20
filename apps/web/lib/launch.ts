import type { PartnerType, Plan } from "@repo/contracts";
import { skew } from "./format";

/** One top city's launch actions (J18). Deterministic: every value is copied from the plan, nothing is generated. */
export type LaunchRow = {
  city: string;
  country: string;
  lat: number;
  lon: number;
  radius_km: number | null;
  languages: string[];
  partners: { type: string; name: string; lift: number | null }[];
};

const LOCAL_TYPES = ["artist", "podcast", "movie"] as const;

export function launchRows(plan: Plan, take = 3): LaunchRow[] {
  return plan.cities.slice(0, take).map((c) => ({
    city: c.name,
    country: c.country,
    lat: c.lat,
    lon: c.lon,
    radius_km: c.radius_m ? c.radius_m / 1000 : null,
    languages: c.languages ?? [],
    partners: LOCAL_TYPES.flatMap((t) =>
      (plan.partners[t] ?? []).filter((p) => p.city === c.name).map((p) => ({ type: t, name: p.name, lift: p.lift ?? null })),
    )
      .sort((a, b) => (b.lift ?? 0) - (a.lift ?? 0))
      .slice(0, 3),
  }));
}

/** "Strongest age band 25-29 (+0.8%); leans male (+28.0%)", from Qloo's demographics call (whole audience). */
export function audienceLine(plan: Plan): string | null {
  const a = plan.audience;
  if (!a?.age.length || !a.gender.length) return null;
  const age = a.age.reduce((x, y) => (y.index > x.index ? y : x));
  const g = a.gender.reduce((x, y) => (y.index > x.index ? y : x));
  return `Strongest age band ${age.band} (${skew(age.index)}); leans ${g.label} (${skew(g.index)})`;
}

const partnerText = (p: LaunchRow["partners"][number]) => `${p.name} (${p.type}${p.lift ? `, ×${p.lift.toFixed(2)}` : ""})`;

export function launchMarkdown(plan: Plan, rows: LaunchRow[]): string {
  const aud = audienceLine(plan);
  const out = [`# Launch actions: ${plan.input.game.title}`, ""];
  rows.forEach((r, i) => {
    out.push(`## ${i + 1}. ${r.city}, ${r.country}`, "");
    out.push(`- [ ] Localise into: ${r.languages.join(", ") || "not in this saved plan"}`);
    out.push(
      `- [ ] Geo-target ${r.city}: ${r.lat}, ${r.lon}` + (r.radius_km != null ? `, ${r.radius_km} km radius` : ""),
    );
    out.push(`- [ ] Approach local partners: ${r.partners.map(partnerText).join("; ") || "none in this plan"}`);
    if (aud) out.push(`- [ ] Target the audience: ${aud}`);
    out.push("");
  });
  out.push("Languages come from a static table, not Qloo. Partners are ranked by lift against all gamers in the city.");
  out.push("Spawn scores are an affinity index, not a sales forecast.");
  return out.join("\n");
}

const cell = (v: string | number | null) => {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

/** A plain CSV for spreadsheets. Not any ad platform's import format. */
export function launchCsv(plan: Plan, rows: LaunchRow[]): string {
  const aud = audienceLine(plan) ?? "";
  const head = ["rank", "city", "country", "latitude", "longitude", "radius_km", "languages", "partner_1", "partner_2", "partner_3", "audience_skew"];
  const body = rows.map((r, i) =>
    [i + 1, r.city, r.country, r.lat, r.lon, r.radius_km, r.languages.join("; "), ...[0, 1, 2].map((k) => (r.partners[k] ? partnerText(r.partners[k]) : "")), aud]
      .map(cell)
      .join(","),
  );
  return [head.join(","), ...body].join("\n") + "\n";
}

/** Where to market first: partner types ordered by the median lift of the plan's global list (Qloo data only). */
export function channels(plan: Plan): { kind: PartnerType; lift: number }[] {
  const kinds: PartnerType[] = ["artist", "podcast", "movie", "brand"];
  const median = (xs: number[]) => {
    const s = [...xs].sort((a, b) => a - b);
    const m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
  };
  return kinds
    .map((kind) => ({
      kind,
      lifts: (plan.partners[kind] ?? []).filter((p) => !p.city && p.lift != null).map((p) => p.lift!),
    }))
    .filter((c) => c.lifts.length >= 3)
    .map((c) => ({ kind: c.kind, lift: median(c.lifts) }))
    .sort((a, b) => b.lift - a.lift);
}
