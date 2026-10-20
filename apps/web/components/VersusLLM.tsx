"use client";

import { useState } from "react";
import Link from "next/link";
import type { LLMOnly, PartnerType, Plan } from "@repo/contracts";
import { api, ApiError } from "../lib/api";

const LABEL: Record<PartnerType, string> = { artist: "Artists", podcast: "Podcasts", movie: "Films", brand: "Brands" };
const SAMPLE = /^sample(-[a-z]+)?$/;

/** The same question put to an LLM with no Qloo data, every name it gives checked in Qloo. A labelled baseline. */
export function VersusLLM({ plan }: { plan: Plan }) {
  const [data, setData] = useState<LLMOnly | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      setData(
        SAMPLE.test(plan.id)
          ? ((await (await fetch(`/${plan.id}-llm-only.json`)).json()) as LLMOnly)
          : await api.llmOnly(plan.id),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load the comparison.");
    } finally {
      setBusy(false);
    }
  }

  const names = Object.fromEntries(plan.cities.map((c) => [c.region_id, c.name]));
  return (
    <section className="section stack" aria-labelledby="vs-h">
      <h2 id="vs-h" className="h2">
        Qloo vs an LLM alone<span className="h-sub">: same inputs, no taste data</span>
      </h2>
      <p className="muted" style={{ maxWidth: 760 }}>
        We ask an LLM the same question with the same inputs and no Qloo data, then look up every name it gives in Qloo
        and score it the same way: how much more your comps&apos; fans like it than gamers in general (×lift).
      </p>
      {!data && (
        <p>
          <button className="btn" onClick={load} disabled={busy} data-testid="vs-load">
            {busy ? "Asking the LLM…" : "Compare with an LLM alone"}
          </button>
        </p>
      )}
      {error && (
        <p className="hint" role="alert">
          {error}
        </p>
      )}
      {data && (
        <>
          <div className="vs-grid" data-testid="vs-partners">
            {data.partners.map((k) => {
              const ours = (plan.partners[k.kind] ?? []).filter((p) => !p.city).slice(0, 6);
              return (
                <div className="card stack" key={k.kind}>
                  <div className="spread">
                    <h3 className="h3">{LABEL[k.kind]}</h3>
                    <span className="label muted">
                      median ×{k.qloo_median_lift?.toFixed(2) ?? "–"} vs ×{k.median_lift?.toFixed(2) ?? "–"}
                    </span>
                  </div>
                  <div className="vs-cols">
                    <div>
                      <span className="label">Qloo, measured</span>
                      <ol className="vs-list">
                        {ours.map((p) => (
                          <li key={p.entity_id}>
                            {p.name} <span className="num muted">×{p.lift?.toFixed(2) ?? "–"}</span>
                          </li>
                        ))}
                      </ol>
                    </div>
                    <div>
                      <span className="label">LLM only</span>
                      <ol className="vs-list">
                        {k.picks.map((p) => (
                          <li key={p.name}>
                            {p.name}{" "}
                            {p.entity_id == null ? (
                              <span className="hint">not in Qloo</span>
                            ) : p.lift == null ? (
                              <span className="hint">no score</span>
                            ) : (
                              <>
                                <span className="num muted">×{p.lift.toFixed(2)}</span>
                                {p.lift <= 1 && <span className="vs-flat"> gamers like it as much</span>}
                              </>
                            )}
                          </li>
                        ))}
                      </ol>
                    </div>
                  </div>
                  <span className="hint">
                    {k.found} of {k.picks.length} found in Qloo · {k.overlap} also on Qloo&apos;s list
                  </span>
                </div>
              );
            })}
          </div>
          <div className="card stack">
            <h3 className="h3">Where to launch: top 5 cities</h3>
            <div className="vs-cols">
              <div>
                <span className="label">Qloo spawn score</span>
                <ol className="vs-list">
                  {plan.cities.slice(0, 5).map((c) => (
                    <li key={c.region_id}>{c.name}</li>
                  ))}
                </ol>
              </div>
              <div>
                <span className="label">LLM only</span>
                <ol className="vs-list">
                  {data.cities.slice(0, 5).map((r) => (
                    <li key={r}>{names[r] ?? r}</li>
                  ))}
                </ol>
              </div>
            </div>
            <span className="hint">
              On cities, the LLM matched Google Trends more often on our held-out games.{" "}
              <Link className="textlink" href="/accuracy">
                See the evaluation
              </Link>
              .
            </span>
          </div>
          <p className="hint">
            LLM: {data.model}, temperature 0. Its names and cities are not from Qloo and are never used in the plan.
            Lift for its names is Qloo&apos;s measurement, and Qloo picked its own list by lift, so that column favours
            Qloo by design; the{" "}
            <Link className="textlink" href="/accuracy">
              partner check
            </Link>{" "}
            measures the difference without Qloo&apos;s scores.
          </p>
        </>
      )}
    </section>
  );
}
