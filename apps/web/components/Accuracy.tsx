import Link from "next/link";
import results from "../public/eval-results.json";
import audience from "../public/audience-check.json";
import { Notice } from "./ui";

/** Written by apps/api/scripts/scenarios.py score: never edit these numbers by hand. */
export const AUDIENCE = audience;
export const EVAL = results;

type Method = { method: string; n: number; top1: number; top3: number; rho: number };
type Row = (typeof results.holdout.scenarios)[number];

const byName = (ms: Method[], prefix: string) => ms.find((m) => m.method.startsWith(prefix));

/** Landing-page summary: held-out headline numbers for Crowdspawn, an LLM alone and popularity. */
export function AccuracySummary() {
  const h = EVAL.holdout;
  const ours = byName(h.methods, "Crowdspawn")!;
  const llm = byName(h.methods, "LLM only");
  const pop = byName(h.methods, "Popularity");
  const top = h.top_cities[0]!;
  return (
    <section className="section stack" aria-labelledby="acc-h">
      <h2 id="acc-h" className="h2">
        How accurate is it?
      </h2>
      <p style={{ maxWidth: 760 }}>
        We hid {h.n} games with no home-country setting, then checked which country Google Trends ranks first for a real
        shipped game like each one. The top market was found in:
      </p>
      <div className="hud" data-testid="accuracy-numbers">
        {[ours, llm, pop].filter(Boolean).map((m) => (
          <div className="stat" key={m!.method}>
            <span className="label muted">{m!.method}</span>
            <b className="num">
              {m!.top1} of {m!.n}
            </b>
            <span className="hint">
              top 3: {m!.top3} of {m!.n}
            </span>
          </div>
        ))}
      </div>
      <p className="muted" style={{ maxWidth: 760 }}>
        {llm && llm.top1 > ours.top1
          ? "On these games an LLM without Qloo data found it more often than Crowdspawn's ranking"
          : "On these games Crowdspawn found it at least as often as an LLM without Qloo data"}
        , and the ranking has a city bias: {top.city} came first for {top.games} of the {h.n} games. Trends measures
        search interest, not sales, and the samples are small. Use the ranking as a starting hypothesis, not a forecast.
      </p>
      <p style={{ maxWidth: 760 }}>
        <b>The audience data checks out.</b> Qloo&apos;s gender skew orders {AUDIENCE.rows.length} genres the way a
        survey of about 270,000 gamers does (ρ {AUDIENCE.rho_qloo}). An LLM&apos;s guess matched too (ρ{" "}
        {AUDIENCE.rho_llm}), but Qloo measures it for your exact comp set.
      </p>
      <p>
        <Link className="textlink" href="/accuracy">
          See every game and baseline
        </Link>
      </p>
    </section>
  );
}

const country = (a2: string) => new Intl.DisplayNames(["en"], { type: "region" }).of(a2) ?? a2;

/** On a sample plan: what the evaluation found for this one game, from the same JSON (J19). Facts only. */
export function SampleCallout({ game }: { game: string }) {
  const row = EVAL.tuning.scenarios.find((r) => r.game.startsWith(`${game}:`));
  if (!row) return null;
  const ours = byName(EVAL.holdout.methods, "Crowdspawn")!;
  const llm = byName(EVAL.holdout.methods, "LLM only");
  return (
    <Notice>
      <b>Checked for this game:</b> among the countries we score, Google Trends puts{" "}
      {country(row.truth_top3[0]!)} first for {row.truth}
      {row.cancelled ? " (cancelled, never shipped)" : ""}, a real game like it. In our evaluation Crowdspawn&apos;s #1
      city was {row.crowdspawn_city}; an LLM without Qloo data put {country(row.llm_top3[0]!)} first. This game is
      from the set the scorer was designed on
      {llm && llm.top1 > ours.top1
        ? `, and on ${EVAL.holdout.n} held-out games the LLM found the top country more often (${llm.top1} vs ${ours.top1})`
        : ""}
      .{" "}
      <Link className="textlink" href="/accuracy">
        All results
      </Link>
    </Notice>
  );
}

function MethodTable({ methods, caption }: { methods: Method[]; caption: string }) {
  return (
    <div className="table-wrap">
      <table className="trace">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th>Method</th>
            <th>Trends #1 is our #1</th>
            <th>Trends #1 in our top 3</th>
            <th>Mean ρ</th>
          </tr>
        </thead>
        <tbody>
          {methods.map((m) => (
            <tr key={m.method}>
              <td>{m.method}</td>
              <td className="num">
                {m.top1} of {m.n}
              </td>
              <td className="num">
                {m.top3} of {m.n}
              </td>
              <td className="num">{m.rho}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScenarioTable({ rows, caption }: { rows: Row[]; caption: string }) {
  return (
    <div className="table-wrap">
      <table className="trace">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th>Hypothetical game</th>
            <th>Real game used as truth</th>
            <th>Trends top 3</th>
            <th>Crowdspawn top 3 (#1 city)</th>
            <th>LLM-only top 3</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.game}>
              <td>{r.game}</td>
              <td>
                {r.truth}
                {r.cancelled ? " (cancelled, never shipped)" : ""}
              </td>
              <td className="num">{r.truth_top3.join(", ")}</td>
              <td className="num">
                {r.crowdspawn_hit ? "✓ " : ""}
                {r.crowdspawn_top3.join(", ")} ({r.crowdspawn_city})
              </td>
              <td className="num">
                {r.llm_hit ? "✓ " : ""}
                {r.llm_top3.join(", ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The full evaluation, rendered from the same JSON as the landing summary. */
export function AccuracyReport() {
  const { holdout: h, tuning: t } = EVAL;
  const ours = byName(h.methods, "Crowdspawn")!;
  const llm = byName(h.methods, "LLM only");
  return (
    <article className="stack" style={{ paddingTop: 32 }}>
      <header className="stack">
        <span className="label muted">Evaluation</span>
        <h1 className="h1">How accurate is it?</h1>
        <p className="lede" style={{ maxWidth: 820 }}>
          Each test is a hypothetical game with comparable games. Truth is Google Trends interest by country for a real
          shipped game like it, which is never used as a comp. Every method ranks the same candidate countries. ✓ marks a
          correct #1.
        </p>
      </header>

      <section className="section stack" aria-labelledby="ho-h">
        <h2 id="ho-h" className="h2">
          Held-out set: {h.n} games with no home-country setting
        </h2>
        <p className="muted" style={{ maxWidth: 760 }}>
          Written and committed before it was ever scored, with the scorer frozen.{" "}
          {llm && llm.top1 > ours.top1 ? "Crowdspawn lost to an LLM with no Qloo data here. " : ""}Its #1 city was {h.top_cities.map((c) => `${c.city} for ${c.games}`).join(" and ")} of the{" "}
          {h.n} games, whatever the genre. Removing that city bias afterwards did not close the gap (section 4 of{" "}
          <code>docs/scenario-results.md</code>).
        </p>
        <MethodTable methods={h.methods} caption="Held-out results by method" />
        <ScenarioTable rows={h.scenarios} caption="Held-out results by game" />
      </section>

      <section className="section stack" aria-labelledby="tu-h">
        <h2 id="tu-h" className="h2">
          Tuning set: {t.n} games
        </h2>
        <p className="muted" style={{ maxWidth: 760 }}>
          The scorer was designed on these games, so they are a sanity check, not a test. Half have a real-world
          setting, where culture anchors carry the signal. One truth game, Mumbai Gullies, was cancelled and never
          shipped; without it the results are:{" "}
          {t.shipped_only.map((m) => `${m.method} ${m.top1} of ${m.n}`).join(", ")}.
        </p>
        <MethodTable methods={t.methods} caption="Tuning results by method" />
        <ScenarioTable rows={t.scenarios} caption="Tuning results by game" />
      </section>

      <section className="section stack" aria-labelledby="aud-h">
        <h2 id="aud-h" className="h2">
          Audience check: Qloo&apos;s gender skew vs a player survey
        </h2>
        <p className="muted" style={{ maxWidth: 760 }}>
          For {audience.rows.length} genres, Qloo&apos;s female index for a panel of well-known games against the female
          share of each genre&apos;s players in Quantic Foundry&apos;s 2017 survey (about 270,000 gamers). Design fixed
          before any call. Spearman ρ <b>{audience.rho_qloo}</b>
          {audience.rho_llm !== null && (
            <>
              ; an LLM&apos;s guess ({audience.llm_model}) {audience.rho_llm}, which may be recall of this published
              survey. Qloo measures the skew for any comp set, including ones no survey covers
            </>
          )}
          .
        </p>
        <div className="table-wrap">
          <table className="trace" data-testid="audience-check">
            <caption className="sr-only">Female share by genre: survey vs Qloo</caption>
            <thead>
              <tr>
                <th>Genre</th>
                <th>Survey: % female</th>
                <th>Qloo female index</th>
              </tr>
            </thead>
            <tbody>
              {audience.rows.map((r) => (
                <tr key={r.genre}>
                  <td>{r.genre}</td>
                  <td className="num">{r.survey_female_pct}</td>
                  <td className="num">{(r.qloo_female_index > 0 ? "+" : "") + r.qloo_female_index.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section limits" aria-labelledby="cav-h">
        <h2 id="cav-h" className="h3">
          Caveats
        </h2>
        <ul>
          <li>Google Trends measures search interest share per country, not downloads, wishlists or sales.</li>
          <li>Truth is country level; Crowdspawn ranks cities, averaged per country here.</li>
          <li>Small samples: one game moves a hit rate by several points.</li>
          <li>Each LLM ran once, at temperature 0, on one prompt.</li>
          <li>
            Method, code and every number: <code>docs/scenario-results.md</code>,{" "}
            <code>docs/backtest-results.md</code> and <code>docs/audience-check.md</code> in the repository.
          </li>
        </ul>
      </section>
    </article>
  );
}
