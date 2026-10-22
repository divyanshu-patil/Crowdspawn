import type { City, PartnerType, Plan } from "@repo/contracts";
import { pct, usd } from "../lib/format";
import { channels } from "../lib/launch";

const KIND: Record<PartnerType, string> = { artist: "Music artists", podcast: "Podcasts", movie: "Films", brand: "Brands" };

/** ×1.21 → "+21%": how far above (or below) the average gamer, in plain words. */
export const vsAvg = (x: number) => `${x >= 1 ? "+" : "−"}${Math.round(Math.abs(x - 1) * 100)}%`;

/** Plain-language charts of the plan's Qloo numbers, for studios that don't read stats. */
export function PlanCharts({ plan }: { plan: Plan }) {
  if (plan.cities.length < 3) return null;
  return (
    <section className="section stack" aria-labelledby="charts-h">
      <div className="spread">
        <h2 id="charts-h" className="h2">
          Your plan at a glance<span className="h-sub">: what the data says, in pictures</span>
        </h2>
        <span className="label muted">Qloo data only · a guide, not a sales forecast</span>
      </div>
      <div className="charts-grid">
        <WhyCities cities={plan.cities.slice(0, 6)} />
        <Budget plan={plan} />
        <Channels plan={plan} />
        <Overlooked plan={plan} />
      </div>
      <Rollout plan={plan} />
    </section>
  );
}

function Chart({ title, ask, takeaway, children }: { title: string; ask: string; takeaway?: string; children: React.ReactNode }) {
  return (
    <figure className="card stack chart">
      <figcaption>
        <span className="label muted">{ask}</span>
        <h3 className="h3">{title}</h3>
      </figcaption>
      {children}
      {takeaway && (
        <p className="takeaway">
          <b>In short:</b> {takeaway}
        </p>
      )}
    </figure>
  );
}

/** One plain bar per row; length is the share of the biggest value. */
function Bars({ rows }: { rows: { key: string; name: string; v: number; text: string; hot?: boolean; sub?: string }[] }) {
  const max = Math.max(...rows.map((r) => r.v), 0.0001);
  return (
    <div className="bars">
      {rows.map((r, i) => (
        <div key={r.key} className="bar-row" title={`${r.name}: ${r.text}`}>
          <span className="bar-name">
            {r.name}
            {r.sub && <span className="hint"> {r.sub}</span>}
          </span>
          <span className="bar-track" aria-hidden>
            <i className={r.hot ? "hot" : ""} style={{ width: `${Math.max(2, (r.v / max) * 100)}%`, ["--i" as string]: i }} />
          </span>
          <span className="num bar-val">{r.text}</span>
        </div>
      ))}
    </div>
  );
}

const FACTORS: { k: string; v: (c: City) => number | null | undefined; why: string }[] = [
  { k: "Like your kind of game", v: (c) => c.lift, why: "fans of games like yours" },
  { k: "Play on your platforms", v: (c) => c.platform_fit, why: "players on your platforms" },
  { k: "Like your setting", v: (c) => c.culture_fit, why: "fans of your setting's films, shows and music" },
];

function WhyCities({ cities }: { cities: City[] }) {
  const cols = FACTORS.filter((f) => cities.some((c) => f.v(c) != null));
  const max = Math.max(0.01, ...cities.flatMap((c) => cols.map((f) => Math.abs((f.v(c) ?? 1) - 1))));
  const top = cities[0]!;
  const best = cols.reduce((a, b) => ((b.v(top) ?? 0) > (a.v(top) ?? 0) ? b : a));
  return (
    <Chart
      ask="Why these cities?"
      title="What makes each city a good fit"
      takeaway={`${top.name} leads mostly thanks to ${best.why} (${vsAvg(best.v(top)!)} vs the average gamer).`}
    >
      <p className="hint">Compared with the average gamer in each city. Bars to the right are better than average.</p>
      <div className="factors" style={{ ["--cols" as string]: cols.length }}>
        <span />
        {cols.map((f) => (
          <span key={f.k} className="label muted">
            {f.k}
          </span>
        ))}
        {cities.map((c, i) => (
          <div key={c.region_id} className="factors-row">
            <span className="factors-name">{c.name}</span>
            {cols.map((f) => {
              const v = f.v(c);
              if (v == null) return <span key={f.k} className="hint">–</span>;
              return (
                <span key={f.k} className="factors-cell" title={`${c.name}: ${vsAvg(v)} ${f.why}`}>
                  <span className="skew-track" aria-hidden>
                    <i className={v >= 1 ? "pos" : "neg"} style={{ width: `${(Math.abs(v - 1) / max) * 50}%`, ["--i" as string]: i }} />
                  </span>
                  <span className="num">{vsAvg(v)}</span>
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </Chart>
  );
}

function Budget({ plan }: { plan: Plan }) {
  const funded = plan.cities.filter((c) => c.budget_share > 0).slice(0, 6);
  if (!funded.length) return null;
  const top3 = plan.cities.slice(0, 3).reduce((s, c) => s + c.budget_share, 0);
  return (
    <Chart
      ask="Where should my money go?"
      title="Suggested ad budget split"
      takeaway={`About ${Math.round(top3)}% of your budget goes to your top 3 cities. Spend there first.`}
    >
      <Bars
        rows={funded.map((c, i) => ({
          key: c.region_id,
          name: c.name,
          v: c.budget_share,
          text: c.budget_usd != null ? `${pct(c.budget_share)} · ${usd(c.budget_usd)}` : pct(c.budget_share),
          hot: i < 3,
        }))}
      />
    </Chart>
  );
}

function Channels({ plan }: { plan: Plan }) {
  const ranked = channels(plan);
  if (!ranked.length) return null;
  const first = ranked[0]!;
  return (
    <Chart
      ask="Where do I promote it?"
      title="Best places to reach your fans"
      takeaway={`${KIND[first.kind]} work best: your fans like the top picks ${Math.round((first.lift - 1) * 100)}% more than the average gamer does.`}
    >
      <p className="hint">How much more your fans like the top picks in each medium than the average gamer does.</p>
      <Bars
        rows={ranked.map((c, i) => ({
          key: c.kind,
          name: KIND[c.kind],
          v: Math.max(0, c.lift - 1),
          text: vsAvg(c.lift),
          hot: i === 0,
          sub: i === 0 ? "· start here" : undefined,
        }))}
      />
    </Chart>
  );
}

/** Cities that rank far higher for this game than for gamers overall: usually cheaper attention. */
function Overlooked({ plan }: { plan: Plan }) {
  const hidden = (plan.hidden_markets ?? []).slice(0, 5);
  if (!hidden.length) return null;
  const n = plan.cities.length;
  const at = (rank: number) => `${((rank - 1) / Math.max(1, n - 1)) * 100}%`;
  const h = hidden[0]!;
  return (
    <Chart
      ask="Where are the hidden gems?"
      title="Cities other games overlook"
      takeaway={`${h.name} is only #${h.gamer_rank} for gamers overall but #${h.rank} for your game. It's easy to miss if you only follow where most gamers are.`}
    >
      <p className="hint">
        <span className="dot-key grey" /> rank among all gamers → <span className="dot-key green" /> rank for your game (#1 is best)
      </p>
      <div className="jumps">
        {hidden.map((m) => (
          <div key={m.region_id} className="jump-row" title={`${m.name}: #${m.gamer_rank} for all gamers, #${m.rank} for your game`}>
            <span className="bar-name">{m.name}</span>
            <span className="jump-track" aria-hidden>
              <i className="jump-line" style={{ left: at(m.rank), right: `calc(100% - ${at(m.gamer_rank)})` }} />
              <i className="jump-dot grey" style={{ left: at(m.gamer_rank) }} />
              <i className="jump-dot green" style={{ left: at(m.rank) }} />
            </span>
            <span className="num bar-val">
              #{m.gamer_rank} → #{m.rank}
            </span>
          </div>
        ))}
      </div>
    </Chart>
  );
}

/** A roll-out order built from rank and confidence. No dates or results are predicted. */
function Rollout({ plan }: { plan: Plan }) {
  const hidden = new Set((plan.hidden_markets ?? []).map((h) => h.region_id));
  const first = plan.cities.slice(0, 3);
  const next = plan.cities.slice(3, 6);
  const test = plan.cities.slice(6).filter((c) => hidden.has(c.region_id) || c.score > 1).slice(0, 4);
  const waves = [
    { n: "1", title: "Launch here", note: "Your strongest cities. Put most of your effort here on day one.", cities: first },
    { n: "2", title: "Expand next", note: "Add these once the first wave shows what works.", cities: next },
    { n: "3", title: "Test small", note: "Still above average. Try a small ad spend before committing.", cities: test },
  ].filter((w) => w.cities.length);
  return (
    <figure className="card stack chart">
      <figcaption>
        <span className="label muted">What happens after launch?</span>
        <h3 className="h3">A roll-out in waves</h3>
      </figcaption>
      <ol className="waves">
        {waves.map((w) => (
          <li key={w.n} className="wave">
            <span className="wave-n">{w.n}</span>
            <b>{w.title}</b>
            <span className="hint">{w.note}</span>
            <span className="row">
              {w.cities.map((c) => (
                <span key={c.region_id} className="chip" style={{ paddingRight: 14 }} title={`${c.confidence} confidence`}>
                  {c.name}
                </span>
              ))}
            </span>
          </li>
        ))}
      </ol>
      <p className="takeaway">
        <b>After launch:</b> track wishlists and sales per city. If a city does better or worse than its place here, move
        budget towards what works. This order comes from taste data, so treat it as your starting bet, not a forecast.
      </p>
    </figure>
  );
}
