import Link from "next/link";
import type { Plan } from "@repo/contracts";
import sample from "../public/sample-plan.json";
import { SpawnMap } from "../components/SpawnMap";

const plan = sample as unknown as Plan;

export default function Home() {
  return (
    <>
      <section className="hero">
        <h1 className="wordmark">Crowdspawn</h1>
        <div className="tag stack">
          <p className="lede">
            <b>Find where your players already are,</b>
            <br />
            and who else they love,
            <br />
            before launch day.
          </p>
          <div className="row" style={{ justifyContent: "inherit" }}>
            <Link className="btn btn-lg" href="/plan/new">
              Start a plan
            </Link>
            <Link className="ghost" href="/agent">
              Ask the launch agent
            </Link>
            <Link className="ghost" href="/sample">
              See a sample plan
            </Link>
          </div>
        </div>
      </section>

      <section className="section stack">
        <SpawnMap cities={plan.cities} />
        <p className="muted" style={{ maxWidth: 720 }}>
          Sample run for <b>{plan.input.game.title}</b>, an open-world crime game set in Delhi, with comps{" "}
          {plan.comps.map((c) => c.name).join(", ")} and the setting read through{" "}
          {(plan.culture ?? []).map((c) => c.name).join(", ")}. Each crowd shows how much a city over-indexes on taste,
          platform and culture together.
        </p>
      </section>

      <section className="section two-col">
        <h2 className="h1">
          Store tags describe your game. <span className="marker">This describes your players.</span>
        </h2>
        <ol className="quest card">
          {[
            ["Name your rivals", "Pick 1-5 comparable games. Qloo confirms each one exists."],
            ["Name your setting", "Add films, shows or artists from the place your game draws on. Qloo finds their fans."],
            ["Watch the spawn map fill", "Qloo scores 33 cities on taste, platform and culture, live."],
            ["Recruit allies", "Artists, podcasts, films and brands this audience over-indexes on, with Qloo's reasons."],
            ["Take the battle plan", "A budget split and a brief where every claim links to the Qloo call behind it."],
          ].map(([t, d], i) => (
            <li key={t} className="done">
              <span className="box" aria-hidden>
                {i + 1}
              </span>
              <span>
                <b>{t}</b>
                <br />
                <span className="hint">{d}</span>
              </span>
              <span />
            </li>
          ))}
        </ol>
      </section>

      <section className="section limits">
        <h2 className="h3">Honest limits</h2>
        <ul>
          <li>It&apos;s an affinity index from taste data, not a sales or wishlist forecast.</li>
          <li>New indie games are usually not in Qloo yet, so everything runs through comparable games.</li>
          <li>If Qloo is unavailable, Crowdspawn refuses to make a plan rather than guess.</li>
          <li>
            The AI only proposes names and writes words. Qloo must find every game, place and artist, and any number the
            AI writes is checked against Qloo&apos;s results. No personal data is used anywhere.
          </li>
          <li>
            Checked against Google Trends for 10 shipped games, the true #1 country was our #1 in 6 and in our top 3
            in 8. It misses where Qloo&apos;s data is thin, like mobile MOBAs in Southeast Asia. Use it as a starting
            hypothesis and test with small campaigns.
          </li>
        </ul>
      </section>
    </>
  );
}
