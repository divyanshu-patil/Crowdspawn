"use client";

import { useState } from "react";
import Link from "next/link";
import type { City, Plan, PartnerType } from "@repo/contracts";
import { SpawnMap } from "./SpawnMap";
import { Cite, ConfidenceBadge, CONFIDENCE_HELP, CountUp, Notice, RichText, Stat } from "./ui";
import { lift, pct, planToMarkdown, rarity, skew, usd } from "../lib/format";
import { audienceLine, channels, launchCsv, launchMarkdown, launchRows } from "../lib/launch";
import { VersusLLM } from "./VersusLLM";
import { PlanCharts } from "./PlanCharts";
import { AskAI } from "./AskAI";
import { api } from "../lib/api";

const TABS: { key: PartnerType; label: string }[] = [
  { key: "artist", label: "Artists" },
  { key: "podcast", label: "Podcasts" },
  { key: "movie", label: "Films" },
  { key: "brand", label: "Brands" },
];

const TYPE_NAME: Record<string, string> = {
  "urn:entity:movie": "film",
  "urn:entity:tv_show": "show",
  "urn:entity:artist": "artist",
};

const TILTS = [-3, 2, -1.5, 3, -2.5, 1.5, -1, 2.5];

export function PlanView({ plan, traceHref }: { plan: Plan; traceHref: string }) {
  const [activeCity, setActiveCity] = useState<string | null>(null);
  const top = plan.cities[0];
  const maxScore = Math.max(...plan.cities.map((c) => c.score), 1.01);
  const culture = plan.culture ?? [];
  const hidden = plan.hidden_markets ?? []; // plans saved before hidden markets existed have none
  const counts = { high: 0, medium: 0, low: 0 };
  plan.cities.forEach((c) => counts[c.confidence]++);

  return (
    <article className="stack">
      {/* 1. Header */}
      <header className="stack" style={{ paddingTop: 32 }}>
        <span className="label muted">Launch plan · {plan.created_at.slice(0, 10)}</span>
        <h1 className="h1">
          <span className="marker">{plan.input.game.title}</span>
        </h1>
        <p className="lede" style={{ maxWidth: 820 }}>
          Fans of {plan.comps.map((c) => c.name).join(", ")}
          {culture.length > 0 && <> and of {culture.map((c) => c.name).join(", ")}</>} gather most in{" "}
          <strong>{top ? top.name : "—"}</strong>
          {top ? ` (spawn score ${lift(top.score)})` : ""}.
        </p>
        <div className="hud">
          <Stat label="Top spawn point">{top?.name ?? "—"}</Stat>
          <Stat label="Cities scored">
            <CountUp value={plan.cities.length} />
          </Stat>
          <Stat label="Confidence">
            <span title={CONFIDENCE_HELP} style={{ fontSize: 18 }}>
              {counts.high} high · {counts.medium} medium · {counts.low} low
            </span>
          </Stat>
          <Stat label="Qloo calls (live / cached)">
            <CountUp value={plan.calls.live} /> / <CountUp value={plan.calls.cached} />
          </Stat>
          <Stat label="Brief by">
            <span style={{ fontSize: 18 }}>
              {plan.brief?.source === "llm" ? `${plan.brief.provider} · ${plan.brief.model}` : "Template"}
            </span>
          </Stat>
        </div>
      </header>

      {/* 2. The same question to an LLM alone, checked in Qloo: a labelled baseline */}
      <VersusLLM plan={plan} />

      {plan.warnings.filter((w) => w.code !== "low_confidence_city").length > 0 && (
        <Notice tone="warn">
          <ul style={{ marginLeft: 16 }}>
            {plan.warnings
              .filter((w) => w.code !== "low_confidence_city")
              .map((w, i) => (
                <li key={i}>{w.message}</li>
              ))}
          </ul>
        </Notice>
      )}

      {/* 3. Top cities */}
      <section className="section stack" aria-labelledby="cities-h">
        <div className="spread">
          <h2 id="cities-h" className="h2">
            Spawn points<span className="h-sub">: where to launch</span>
          </h2>
          <span className="label muted">Spawn score: taste × platform × culture · not a sales forecast</span>
        </div>
        <SpawnMap
          cities={plan.cities}
          activeId={activeCity}
          onSelect={(id) => {
            setActiveCity(id);
            const row = document.getElementById(`city-${id}`) as HTMLDetailsElement | null;
            if (row) row.open = true; // the map flies to the city; the page stays where it is
          }}
        />
        <ol className="cities">
          {plan.cities.map((c, i) => (
            <CityRow
              key={c.region_id}
              c={c}
              i={i}
              maxScore={maxScore}
              active={activeCity === c.region_id}
              onToggle={() => setActiveCity(c.region_id)}
              planId={plan.id}
              traceHref={traceHref}
              hasBudget={plan.input.budget_usd != null}
            />
          ))}
        </ol>
        {hidden.length > 0 && (
          <div className="card stack hidden-markets" aria-label="Hidden markets">
            <span className="label">Hidden markets</span>
            <p className="muted">
              Cities that rank far higher for your game than for gamers overall. Easy to miss if you only follow market
              size.
            </p>
            <ul style={{ marginLeft: 16 }}>
              {hidden.map((h) => (
                <li key={h.region_id}>
                  <b>{h.name}</b>: #{h.rank} for your game, #{h.gamer_rank} for gamers overall
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* 3b. The plan at a glance: plain-language charts of the same Qloo numbers */}
      <PlanCharts plan={plan} />

      {/* Expanded comps with Qloo's explanations */}
      <section className="section stack" aria-labelledby="comps-h">
        <h2 id="comps-h" className="h2">
          Rivals<span className="h-sub">: games your fans also love</span>
        </h2>
        <p className="muted">
          Your comps, then the games Qloo says their fans also love, with why. <Cite id={plan.expanded[0]?.result_id ?? "q2"} traceHref={traceHref} />
        </p>
        <div className="scatter">
          {plan.comps.map((c, i) => (
            <figure
              key={c.entity_id}
              className="polaroid"
              style={{ ["--r" as string]: `${TILTS[i % TILTS.length]}deg`, ["--i" as string]: i, ["--w" as string]: "190px" }}
            >
              {c.image_url ? <img src={c.image_url} alt="" loading="lazy" /> : <div className="ph">{c.name[0]}</div>}
              <figcaption>
                <span className="label muted">Your comp</span>
                <br />
                <b>{c.name}</b>
              </figcaption>
            </figure>
          ))}
        </div>
        {culture.length > 0 && (
          <p className="row" aria-label="Culture anchors">
            <span className="label muted">Setting, via</span>
            {culture.map((a) => (
              <span key={a.entity_id} className="chip" style={{ paddingRight: 14 }}>
                {a.name}
                <span className="muted">{TYPE_NAME[a.type] ?? ""}</span>
              </span>
            ))}
            <Cite id={culture[0]!.result_id} traceHref={traceHref} />
          </p>
        )}
        <div className="loot-grid">
          {plan.expanded.slice(0, 12).map((g, i) => (
            <div key={g.entity_id} className="loot" style={{ ["--i" as string]: i }}>
              <span className="label muted">Affinity {(g.affinity * 100).toFixed(1)}</span>
              <span className="name">{g.name}</span>
              <span className="why">{g.why}</span>
            </div>
          ))}
        </div>
      </section>

      {/* 4. Audience */}
      {plan.audience && (
        <section className="section two-col" aria-labelledby="aud-h">
          <div className="stack">
            <h2 id="aud-h" className="h2">
              Who&apos;s in the party<span className="h-sub">: your audience by age and gender</span>
            </h2>
            <p className="muted">
              How this audience over- or under-indexes against the average, by age and gender. Source: Qloo
              demographics <Cite id={plan.audience.result_id} traceHref={traceHref} />
            </p>
          </div>
          <div className="card">
            {[...plan.audience.age.map((b) => ({ k: b.band, v: b.index })), ...plan.audience.gender.map((g) => ({ k: g.label, v: g.index }))].map(
              (row, i) => {
                const w = Math.min(50, Math.abs(row.v) * 100);
                return (
                  <div className="skew" key={row.k}>
                    <span className="label">{row.k}</span>
                    <div className="skew-track" aria-hidden>
                      <i className={row.v >= 0 ? "pos" : "neg"} style={{ width: `${w}%`, ["--i" as string]: i }} />
                    </div>
                    <span className="num" style={{ textAlign: "right" }}>
                      {skew(row.v)}
                    </span>
                  </div>
                );
              },
            )}
          </div>
        </section>
      )}

      {/* 5. Partners */}
      <Partners plan={plan} traceHref={traceHref} />

      {/* 5b. Launch actions: deterministic, copied from the plan */}
      <LaunchActions plan={plan} />

      {/* 6. Gap view */}
      {plan.gap && (
        <section className="section stack" aria-labelledby="gap-h">
          <h2 id="gap-h" className="h2">
            The gap from your last game <Cite id={plan.gap.result_id} traceHref={traceHref} />
          </h2>
          <div className="two-col">
            <div className="card stack">
              <span className="label">New ground: only the target audience</span>
              <div className="row">{plan.gap.target_only.map((t) => <span key={t} className="chip" style={{ paddingRight: 14 }}>{t}</span>)}</div>
            </div>
            <div className="card stack">
              <span className="label">Shared with your current players</span>
              <div className="row">{plan.gap.shared.map((t) => <span key={t} className="chip" style={{ paddingRight: 14 }}>{t}</span>)}</div>
            </div>
          </div>
        </section>
      )}

      {/* 7. Brief */}
      {plan.brief && (
        <section className="section stack brief" aria-labelledby="brief-h">
          <div className="spread">
            <h2 id="brief-h" className="h2">
              Battle plan<span className="h-sub">: the brief</span>
            </h2>
            <span className="label muted">
              {plan.brief.source === "llm" ? `Written by ${plan.brief.model}, grounded on Qloo data` : "Template brief"}
            </span>
          </div>
          {plan.brief.notice && <Notice>{plan.brief.notice}</Notice>}
          <div className="card">
            {plan.brief.sections.map((s) => (
              <div key={s.heading}>
                <h3 className="h3">{s.heading}</h3>
                <p>
                  <RichText text={s.body} traceHref={traceHref} />
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 8. Limits — always visible */}
      <section className="section limits" aria-labelledby="limits-h">
        <h2 id="limits-h" className="h3">
          Read this before you spend
        </h2>
        <ul>
          {plan.limits.map((l) => (
            <li key={l}>{l}</li>
          ))}
          {plan.dropped_comps.length > 0 && <li>Comps not found in Qloo and left out: {plan.dropped_comps.join(", ")}.</li>}
        </ul>
      </section>

      {/* 9. Actions */}
      <Actions plan={plan} traceHref={traceHref} />

      <AskAI
        title="Ask AI about this plan"
        note="Answers use only this plan's Qloo data, with citations. No outside knowledge, no forecasts."
        starters={[
          top && `Why is ${top.name} the top spawn point?`,
          "Which partner type should I market through first?",
          plan.audience && "Who is my audience?",
          plan.input.budget_usd != null && "How should I split the budget?",
        ].filter((s): s is string => !!s)}
        ask={(q) => api.ask(plan, q)}
        traceHref={traceHref}
      />
    </article>
  );
}

function CityRow({
  c,
  i,
  maxScore,
  active,
  onToggle,
  traceHref,
  hasBudget,
  planId,
}: {
  c: City;
  i: number;
  maxScore: number;
  active: boolean;
  onToggle: () => void;
  traceHref: string;
  hasBudget: boolean;
  planId: string;
}) {
  const v = Math.max(0.04, c.score / maxScore);
  const [target, pc, mobile, console_, cultureId] = c.result_ids;
  return (
    <li>
      <details
        id={`city-${c.region_id}`}
        className={`city ${active ? "active" : ""}`}
        style={{ ["--i" as string]: i }}
        onToggle={(e) => e.currentTarget.open && onToggle()}
      >
        <summary>
          <span className="rank c-rank">{i + 1}</span>
          <span className="c-name">
            <b>{c.name}</b> <span className="muted">{c.country}</span>
          </span>
          <span className={`power c-power ${i < 3 && c.score > 1 ? "hot" : ""}`} aria-hidden>
            <i style={{ ["--v" as string]: Math.min(1, v), ["--i" as string]: i }} />
          </span>
          <span className="num c-lift" aria-label={`spawn score ${lift(c.score)}`}>
            ×{lift(c.score)}
          </span>
          <span className="c-conf">
            <ConfidenceBadge level={c.confidence} />
          </span>
          <span className="num c-share" style={{ textAlign: "right" }}>
            {pct(c.budget_share ?? 0)}
            {hasBudget && c.budget_usd != null && (
              <>
                <br />
                <span className="muted" style={{ fontSize: 13 }}>
                  {usd(c.budget_usd)}
                </span>
              </>
            )}
          </span>
          <span className="chev" aria-hidden>
            ›
          </span>
        </summary>
        <div className="why">
          <p className="breakdown num" aria-label="Spawn score breakdown">
            <span>
              <b>{lift(c.lift)}</b> taste
            </span>
            ×
            <span>
              <b>{lift(c.platform_fit)}</b> platform
            </span>
            {c.culture_fit != null && (
              <>
                ×
                <span>
                  <b>{lift(c.culture_fit)}</b> culture
                </span>
              </>
            )}
            =<span className="total">{lift(c.score)}</span>
          </p>
          <p>
            <b>Taste:</b> fans of your comp set score <b className="num">{c.target_score.toFixed(3)}</b> on Qloo&apos;s
            affinity rank here, against <b className="num">{c.baseline_score.toFixed(3)}</b> for gamers in general (the
            mean of PC, console and mobile player panels).{" "}
            <b>Platform:</b> how strong your platforms are here compared with gaming overall.
            {c.culture_fit != null && (
              <>
                {" "}
                <b>Culture:</b> how concentrated fans of your setting&apos;s films, shows and artists are here, compared
                with the average city.
              </>
            )}
          </p>
          <p className="muted">
            Based on {c.cells} heatmap cells. {CONFIDENCE_HELP}
          </p>
          <p>
            Sources: <Cite id={target!} traceHref={traceHref} /> your comps
            {pc && (
              <>
                , <Cite id={pc} traceHref={traceHref} /> PC, <Cite id={mobile!} traceHref={traceHref} /> mobile,{" "}
                <Cite id={console_!} traceHref={traceHref} /> console
              </>
            )}
            {cultureId && (
              <>
                , <Cite id={cultureId} traceHref={traceHref} /> culture
              </>
            )}
          </p>
          <p>
            <Link className="textlink" href={`/scout?lat=${c.lat}&lon=${c.lon}&plan=${encodeURIComponent(planId)}`}>
              Scout this city
            </Link>{" "}
            <span className="hint">: what locals play, and a verdict for your game here.</span>
          </p>
        </div>
      </details>
    </li>
  );
}

function Partners({ plan, traceHref }: { plan: Plan; traceHref: string }) {
  const [tab, setTab] = useState<PartnerType>("artist");
  const items = plan.partners[tab] ?? [];
  const ranked = channels(plan);
  return (
    <section className="section" aria-labelledby="partners-h">
      <div className="spread">
        <h2 id="partners-h" className="h2">
          Allies<span className="h-sub">: partners to recruit</span>
        </h2>
        <span className="label muted">Legendary ≥ 95 affinity · Rare ≥ 90</span>
      </div>
      <p className="muted" style={{ marginTop: 8, maxWidth: 760 }}>
        Co-marketing and sponsorship leads: artists for launch events and streams, podcasts for ad reads, films and brands
        for collaborations. Sorted by how much more your fans like each one than gamers in general (×lift). Local picks
        compare against gamers in that city.
      </p>
      {ranked.length > 1 && (
        <p style={{ marginTop: 12, maxWidth: 760 }} data-testid="channels">
          <b>Where to market first:</b>{" "}
          {ranked.map((c, i) => (
            <span key={c.kind}>
              {i > 0 && " › "}
              {TABS.find((t) => t.key === c.kind)!.label} ×{c.lift.toFixed(2)}
            </span>
          ))}
          <span className="muted"> (median lift of each list: the medium where these fans stand out most)</span>
        </p>
      )}
      <div className="tabs" role="tablist" style={{ marginTop: 20 }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            id={`tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls="partner-panel"
            className="tab"
            onClick={() => setTab(t.key)}
          >
            {t.label} ({plan.partners[t.key]?.length ?? 0})
          </button>
        ))}
      </div>
      <div id="partner-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} key={tab}>
        {tab === "brand" && (
          <p className="hint" style={{ marginTop: 14 }}>
            Brands are global: Qloo&apos;s brand affinity does not vary by location.
          </p>
        )}
        {items.length === 0 ? (
          <p className="hint" style={{ marginTop: 14 }}>
            Qloo returned no {tab}s for this audience.
          </p>
        ) : (
          <div className="loot-grid">
            {items.map((p, i) => {
              const tier = rarity(p.affinity);
              return (
                <div key={`${p.entity_id}-${p.city}`} className={`loot ${tier}`} style={{ ["--i" as string]: i }}>
                  <div className="spread">
                    <span className="tier label">{tier}</span>
                    <span className="label muted">{p.city ? `Local · ${p.city}` : "Global"}</span>
                  </div>
                  <span className="name">{p.name}</span>
                  <span className="label">
                    Affinity {(p.affinity * 100).toFixed(1)}
                    {p.lift != null && ` · ×${p.lift.toFixed(2)} vs all gamers${p.city ? " here" : ""}`}
                  </span>
                  <span className="why">{p.why}</span>
                  <span>
                    <Cite id={p.result_id} traceHref={traceHref} />
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

function LaunchActions({ plan }: { plan: Plan }) {
  const [copied, setCopied] = useState(false);
  const rows = launchRows(plan);
  const aud = audienceLine(plan);
  if (!rows.length) return null;
  function download() {
    const url = URL.createObjectURL(new Blob([launchCsv(plan, rows)], { type: "text/csv" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "launch-actions.csv" });
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <section className="section stack" aria-labelledby="actions-h">
      <div className="spread">
        <h2 id="actions-h" className="h2">
          Launch actions<span className="h-sub">: what to do in your top 3 cities</span>
        </h2>
        <div className="row no-print">
          <button
            className="ghost"
            onClick={async () => {
              await navigator.clipboard.writeText(launchMarkdown(plan, rows));
              setCopied(true);
              setTimeout(() => setCopied(false), 1800);
            }}
          >
            {copied ? "Copied ✓" : "Copy checklist"}
          </button>
          <button className="ghost" onClick={download}>
            Download CSV
          </button>
        </div>
      </div>
      <div className="launch-grid">
        {rows.map((r, i) => (
          <div key={r.city} className="card stack launch-card">
            <p>
              <span className="label muted">
                #{i + 1} · {r.country}
              </span>
              <br />
              <b className="h3">{r.city}</b>
            </p>
            <p>
              <span className="label">Localise into</span>
              <br />
              {r.languages.join(", ") || <span className="muted">not in this saved plan</span>}
            </p>
            <p>
              <span className="label">Geo-target</span>
              <br />
              <span className="num">
                {r.lat}, {r.lon}
                {r.radius_km != null && ` · ${r.radius_km} km radius`}
              </span>
            </p>
            <p>
              <span className="label">Local partners</span>
              <br />
              {r.partners.length ? (
                r.partners.map((p) => (
                  <span key={p.name} className="hint" style={{ display: "block" }}>
                    {p.name} <span className="muted">({p.type}{p.lift ? `, ×${p.lift.toFixed(2)}` : ""})</span>
                  </span>
                ))
              ) : (
                <span className="muted">none in this plan</span>
              )}
            </p>
            {aud && (
              <p>
                <span className="label">Audience</span>
                <br />
                <span className="hint">{aud} (whole audience)</span>
              </p>
            )}
          </div>
        ))}
      </div>
      <p className="hint">
        Copied from the plan, with no AI. Languages come from a static table, not Qloo; the radius is the one Qloo&apos;s
        heatmap used. The CSV is a plain spreadsheet, not an ad platform&apos;s import format.
      </p>
    </section>
  );
}

function Actions({ plan, traceHref }: { plan: Plan; traceHref: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="row no-print section">
      <button
        className="ghost"
        onClick={async () => {
          await navigator.clipboard.writeText(planToMarkdown(plan));
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        }}
      >
        {copied ? "Copied ✓" : "Copy as Markdown"}
      </button>
      <button className="ghost" onClick={() => window.print()}>
        Print
      </button>
      <Link className="ghost" href={traceHref}>
        Open Qloo trace
      </Link>
      <Link className="textlink" href="/plan/new">
        Advanced: pick comps yourself
      </Link>
    </div>
  );
}
