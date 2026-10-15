import type { Plan } from "@repo/contracts";

export const lift = (x: number) => x.toFixed(2);
export const pct = (x: number) => `${x.toFixed(x % 1 ? 2 : 0)}%`;
export const usd = (x: number) =>
  x.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });
export const skew = (x: number) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`; // same as the API facts

/** Partner "rarity" from Qloo affinity. Purely a visual tier; thresholds shown in the legend. */
export function rarity(affinity: number): "legendary" | "rare" | "common" {
  if (affinity >= 0.95) return "legendary";
  if (affinity >= 0.9) return "rare";
  return "common";
}

export function planToMarkdown(plan: Plan): string {
  const lines = [`# Launch plan: ${plan.input.game.title}`, ""];
  lines.push(`Comps: ${plan.comps.map((c) => c.name).join(", ")}`, "");
  lines.push("## Cities (affinity index vs mainstream gamers)", "");
  lines.push("| Rank | City | Lift | Confidence | Budget share |", "|---|---|---|---|---|");
  plan.cities.forEach((c, i) =>
    lines.push(
      `| ${i + 1} | ${c.name}, ${c.country} | ${lift(c.lift)} | ${c.confidence} | ${pct(c.budget_share ?? 0)}${
        c.budget_usd != null ? ` (${usd(c.budget_usd)})` : ""
      } |`,
    ),
  );
  if (plan.brief) {
    lines.push("", `## Brief (${plan.brief.source})`, "");
    for (const s of plan.brief.sections) lines.push(`### ${s.heading}`, "", s.body, "");
  }
  lines.push("## Limits", "", ...plan.limits.map((l) => `- ${l}`), "");
  lines.push("_All data from Qloo Taste AI. Citations like [q3] refer to the plan's Qloo call trace._");
  return lines.join("\n");
}
