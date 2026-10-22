import type { City, PartnerType, Plan } from "@repo/contracts";
import { lift } from "../lib/format";

const KIND: Record<PartnerType, string> = { artist: "Artists", podcast: "Podcasts", movie: "Films", brand: "Brands" };
const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
};
const scale = (d0: number, d1: number, r0: number, r1: number) => (v: number) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);

/** Charts drawn only from the plan's Qloo numbers. Hover a mark for its values. */
export function PlanCharts({ plan }: { plan: Plan }) {
  if (plan.cities.length < 3) return null;
  return (
    <section className="section stack" aria-labelledby="charts-h">
      <div className="spread">
        <h2 id="charts-h" className="h2">
          Analytics<span className="h-sub">: the numbers behind the ranking</span>
        </h2>
        <span className="label muted">Qloo data only · affinity index, not a sales forecast</span>
      </div>
      <div className="charts-grid">
        <Factors cities={plan.cities.slice(0, 8)} />
        <TastePlatform cities={plan.cities} />
        <PartnerLift plan={plan} />
        <RankShift plan={plan} />
      </div>
    </section>
  );
}

function Chart({ title, note, children }: { title: string; note: string; children: React.ReactNode }) {
  return (
    <figure className="card stack chart">
      <figcaption>
        <h3 className="h3">{title}</h3>
        <span className="hint">{note}</span>
      </figcaption>
      {children}
    </figure>
  );
}

/** Each factor of the spawn score as a bar from ×1.00 (log scale): right of centre helps, left hurts. */
function Factors({ cities }: { cities: City[] }) {
  const cols: { k: string; v: (c: City) => number | null | undefined }[] = [
    { k: "Taste", v: (c) => c.lift },
    { k: "Platform", v: (c) => c.platform_fit },
  ];
  if (cities.some((c) => c.culture_fit != null)) cols.push({ k: "Culture", v: (c) => c.culture_fit });
  const max = Math.max(0.01, ...cities.flatMap((c) => cols.map((col) => Math.abs(Math.log(col.v(c) ?? 1)))));
  return (
    <Chart title="Why each city ranks" note="Spawn score factors for the top 8. Bars grow from ×1.00: right is above the gamer average.">
      <div className="factors" style={{ ["--cols" as string]: cols.length }}>
        <span />
        {cols.map((c) => (
          <span key={c.k} className="label muted">
            {c.k}
          </span>
        ))}
        {cities.map((c, i) => (
          <div key={c.region_id} className="factors-row">
            <span className="factors-name">{c.name}</span>
            {cols.map((col) => {
              const v = col.v(c);
              if (v == null) return <span key={col.k} className="hint">–</span>;
              const w = (Math.abs(Math.log(v)) / max) * 50;
              return (
                <span key={col.k} className="factors-cell" title={`${c.name} · ${col.k} ×${lift(v)}`}>
                  <span className="skew-track" aria-hidden>
                    <i className={v >= 1 ? "pos" : "neg"} style={{ width: `${w}%`, ["--i" as string]: i }} />
                  </span>
                  <span className="num">{lift(v)}</span>
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </Chart>
  );
}

const W = 460;
const H = 300;
const PAD = { l: 44, r: 16, t: 14, b: 36 };

/** Taste lift against platform fit: top-right cities win on both. Top 3 labelled. */
function TastePlatform({ cities }: { cities: City[] }) {
  const xs = cities.map((c) => c.lift);
  const ys = cities.map((c) => c.platform_fit);
  const pad = (lo: number, hi: number) => [Math.min(lo, 1) - 0.03, Math.max(hi, 1) + 0.03] as const;
  const [x0, x1] = pad(Math.min(...xs), Math.max(...xs));
  const [y0, y1] = pad(Math.min(...ys), Math.max(...ys));
  const x = scale(x0, x1, PAD.l, W - PAD.r);
  const y = scale(y0, y1, H - PAD.b, PAD.t);
  const top = new Set(cities.slice(0, 3).map((c) => c.region_id));
  return (
    <Chart title="Taste vs platform" note="Each dot is a city. Dashed lines mark ×1.00, the gamer average. Top 3 in green.">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart-svg" role="img" aria-label="Scatter of taste lift against platform fit by city">
        <line x1={x(1)} x2={x(1)} y1={PAD.t} y2={H - PAD.b} className="ref" />
        <line x1={PAD.l} x2={W - PAD.r} y1={y(1)} y2={y(1)} className="ref" />
        <line x1={PAD.l} x2={W - PAD.r} y1={H - PAD.b} y2={H - PAD.b} className="axis" />
        <text x={W - PAD.r} y={H - 6} textAnchor="end" className="tick">
          Taste lift →
        </text>
        <text x={PAD.l - 8} y={PAD.t + 4} textAnchor="end" className="tick">
          {lift(y1)}
        </text>
        <text x={PAD.l - 8} y={H - PAD.b} textAnchor="end" className="tick">
          {lift(y0)}
        </text>
        <text x={PAD.l} y={H - PAD.b + 16} className="tick">
          {lift(x0)}
        </text>
        <text transform={`translate(12 ${PAD.t}) rotate(90)`} className="tick">
          Platform fit →
        </text>
        <text x={W - PAD.r - 4} y={PAD.t + 12} textAnchor="end" className="tick strong">
          strong on both
        </text>
        {[...cities].reverse().map((c) => {
          const hot = top.has(c.region_id);
          return (
            <g key={c.region_id} className={hot ? "dot hot" : "dot"}>
              <title>{`${c.name}: spawn ×${lift(c.score)} · taste ×${lift(c.lift)} · platform ×${lift(c.platform_fit)} · ${c.confidence} confidence`}</title>
              <circle cx={x(c.lift)} cy={y(c.platform_fit)} r={12} className="hit" />
              <circle cx={x(c.lift)} cy={y(c.platform_fit)} r={hot ? 6 : 4.5} />
              {hot && (
                <text x={x(c.lift) + 9} y={y(c.platform_fit) + 4} className="tick strong">
                  {c.name}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </Chart>
  );
}

/** Every global partner's lift, one row per medium, with the median marked: where these fans stand out most. */
function PartnerLift({ plan }: { plan: Plan }) {
  const rows = (Object.keys(KIND) as PartnerType[])
    .map((k) => ({ k, items: (plan.partners[k] ?? []).filter((p) => !p.city && p.lift != null) }))
    .filter((r) => r.items.length > 0);
  if (!rows.length) return null;
  const all = rows.flatMap((r) => r.items.map((p) => p.lift!));
  const x0 = Math.min(1, ...all) - 0.05;
  const x1 = Math.max(...all) + 0.05;
  const rh = 46;
  const h = rows.length * rh + 30;
  const x = scale(x0, x1, 90, W - 60);
  return (
    <Chart title="Partner lift by medium" note="Each dot is a global partner; the green tick is the median. Further right: fans like it more than gamers do.">
      <svg viewBox={`0 0 ${W} ${h}`} className="chart-svg" role="img" aria-label="Partner lift by medium">
        <line x1={x(1)} x2={x(1)} y1={4} y2={h - 26} className="ref" />
        <text x={x(1)} y={h - 8} textAnchor="middle" className="tick">
          ×1.00
        </text>
        <text x={W - 60} y={h - 8} textAnchor="end" className="tick">
          ×{lift(x1)}
        </text>
        {rows.map((r, i) => {
          const cy = i * rh + rh / 2 + 4;
          const m = median(r.items.map((p) => p.lift!));
          return (
            <g key={r.k}>
              <text x={0} y={cy + 4} className="tick strong">
                {KIND[r.k]}
              </text>
              <line x1={90} x2={W - 60} y1={cy} y2={cy} className="axis" />
              {r.items.map((p) => (
                <g key={p.entity_id} className="dot">
                  <title>{`${p.name}: ×${lift(p.lift!)} vs all gamers · affinity ${(p.affinity * 100).toFixed(1)}`}</title>
                  <circle cx={x(p.lift!)} cy={cy} r={12} className="hit" />
                  <circle cx={x(p.lift!)} cy={cy} r={5} className="ringed" />
                </g>
              ))}
              <line x1={x(m)} x2={x(m)} y1={cy - 13} y2={cy + 13} className="median" />
              <text x={W} y={cy + 4} textAnchor="end" className="tick num">
                ×{lift(m)}
              </text>
            </g>
          );
        })}
      </svg>
    </Chart>
  );
}

/** Rank among gamers overall (left) against rank for this game (right). Green lines climb: hidden markets. */
function RankShift({ plan }: { plan: Plan }) {
  const cities = plan.cities;
  const byGamers = [...cities].sort((a, b) => b.baseline_score - a.baseline_score || a.region_id.localeCompare(b.region_id));
  const gamerRank = new Map(byGamers.map((c, i) => [c.region_id, i + 1]));
  const hidden = new Set((plan.hidden_markets ?? []).map((h) => h.region_id));
  const step = 18;
  const h = cities.length * step + 34;
  const y = (rank: number) => 26 + (rank - 1) * step;
  const [lx, rx] = [70, 250];
  return (
    <Chart title="Rank shift" note="Left: rank among gamers overall. Right: rank for your game. Green climbs 3+ places: a hidden market.">
      <svg viewBox={`0 0 ${W} ${h}`} className="chart-svg" role="img" aria-label="Rank among all gamers versus rank for this game">
        <text x={lx} y={10} textAnchor="middle" className="tick">
          All gamers
        </text>
        <text x={rx} y={10} textAnchor="middle" className="tick">
          Your game
        </text>
        {[...cities].reverse().map((c) => {
          const i = cities.indexOf(c) + 1;
          const g = gamerRank.get(c.region_id)!;
          const hot = hidden.has(c.region_id);
          return (
            <g key={c.region_id} className={hot ? "slope hot" : "slope"}>
              <title>{`${c.name}: #${g} for gamers overall, #${i} for your game`}</title>
              <line x1={lx} x2={rx} y1={y(g)} y2={y(i)} />
              <circle cx={lx} cy={y(g)} r={3.5} />
              <circle cx={rx} cy={y(i)} r={3.5} />
              <text x={lx - 10} y={y(g) + 4} textAnchor="end" className="tick num">
                {g}
              </text>
              <text x={rx + 10} y={y(i) + 4} className={hot ? "tick strong" : "tick"}>
                {i}. {c.name}
              </text>
            </g>
          );
        })}
      </svg>
    </Chart>
  );
}
