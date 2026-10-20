import { describe, expect, it } from "vitest";
import type { Plan } from "@repo/contracts";
import sample from "../public/sample-delhi-plan.json"; // stable: the hero sample may be regenerated
import { audienceLine, launchCsv, launchMarkdown, launchRows } from "../lib/launch";

// The sample plan with the J11/J18 fields a new plan carries: lift on partners, languages and radius on cities.
const base = sample as unknown as Plan;
const plan: Plan = {
  ...base,
  cities: base.cities.map((c, i) => ({ ...c, radius_m: 30000, languages: i === 0 ? ["Hindi", "Marathi", "English"] : [] })),
  partners: {
    ...base.partners,
    artist: [
      { ...base.partners.artist[0]!, name: "Global act", city: null, lift: 1.5 },
      { ...base.partners.artist[0]!, name: "Low lift, local", city: base.cities[0]!.name, lift: 1.01 },
      { ...base.partners.artist[0]!, name: "High lift, local", city: base.cities[0]!.name, lift: 1.2 },
    ],
    podcast: [{ ...base.partners.artist[0]!, name: "Pod, with a comma", city: base.cities[0]!.name, lift: 1.1 }],
    movie: [{ ...base.partners.artist[0]!, name: "Film \"Quoted\"", city: base.cities[0]!.name, lift: 1.05 }],
  },
};

describe("launch actions (J18)", () => {
  it("takes the top 3 cities and their local partners by lift, never the global ones", () => {
    const rows = launchRows(plan);
    expect(rows.map((r) => r.city)).toEqual(plan.cities.slice(0, 3).map((c) => c.name));
    expect(rows[0]!.partners.map((p) => p.name)).toEqual(["High lift, local", "Pod, with a comma", "Film \"Quoted\""]);
    expect(rows[0]!.radius_km).toBe(30);
    expect(rows[1]!.partners).toEqual([]);
  });

  it("builds a markdown checklist from the plan's own values", () => {
    const md = launchMarkdown(plan, launchRows(plan));
    const c = plan.cities[0]!;
    expect(md).toContain(`## 1. ${c.name}, ${c.country}`);
    expect(md).toContain("- [ ] Localise into: Hindi, Marathi, English");
    expect(md).toContain(`- [ ] Geo-target ${c.name}: ${c.lat}, ${c.lon}, 30 km radius`);
    expect(md).toContain("- [ ] Approach local partners: High lift, local (artist, ×1.20)");
    expect(md).toContain(`- [ ] Target the audience: ${audienceLine(plan)}`);
    expect(md).toContain("static table, not Qloo");
  });

  it("writes a CSV with one row per city and quotes commas and quotes", () => {
    const lines = launchCsv(plan, launchRows(plan)).trimEnd().split("\n");
    expect(lines).toHaveLength(4);
    expect(lines[0]).toBe(
      "rank,city,country,latitude,longitude,radius_km,languages,partner_1,partner_2,partner_3,audience_skew",
    );
    expect(lines[1]).toContain('"Pod, with a comma (podcast, ×1.10)"');
    expect(lines[1]).toContain('"Film ""Quoted"" (movie, ×1.05)"');
    expect(audienceLine(plan)).toBe("Strongest age band 25-29 (+0.8%); leans male (+28.0%)");
  });
});
