"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { AgentRun } from "@repo/contracts";
import { api, ApiError, streamAgent } from "../lib/api";
import { play } from "../lib/sfx";
import { emptyDraft, type Draft } from "../lib/validate";
import { DRAFT_KEY } from "./NewPlanForm";
import { Notice, RichText } from "./ui";

export const EXAMPLES = [
  "A cozy farming and village life game for PC and Switch. Where should I launch first, and who should I partner with?",
  "A fast roguelike deckbuilder for PC and mobile. Which cities over-index for players like mine?",
  "A competitive 5v5 MOBA with anime heroes, mobile first. Where are my players, and which artists should we sponsor?",
  "A detective story game set in 1920s Paris for PC and console. Does the setting help, and where should we launch?",
];

const TOOL_LABEL: Record<string, string> = {
  search_games: "Search games",
  search_culture: "Search culture",
  find_place: "Find a place",
  rank_cities: "Rank cities",
  scout_place: "Scout a place",
  audience: "Read the audience",
  find_partners: "Find partners",
  finish: "Answer",
};

type StepView = { n: number; thought: string; tool: string; args: Record<string, unknown>; obs?: string; ok?: boolean };

/** Handles the server issued ("g1 Stardew Valley (2016)") -> names, so arguments read as words. */
function handleNames(steps: StepView[]): Map<string, string> {
  const names = new Map<string, string>();
  for (const s of steps)
    for (const m of (s.obs ?? "").matchAll(/\b([gcp]\d+) ([^;(\n]+?)(?= \(|;|$)/gm)) names.set(m[1]!, m[2]!.trim());
  return names;
}

function argText(args: Record<string, unknown>, names: Map<string, string>): string {
  return Object.entries(args)
    .filter(([k]) => k !== "answer")
    .map(([k, v]) => {
      const show = (x: unknown) => (typeof x === "string" ? (names.get(x) ?? x) : String(x));
      return `${k}: ${Array.isArray(v) ? v.map(show).join(", ") : show(v)}`;
    })
    .join(" · ");
}

export function LaunchAgent() {
  const router = useRouter();
  const [goal, setGoal] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [steps, setSteps] = useState<StepView[]>([]);
  const [calls, setCalls] = useState({ live: 0, cached: 0 });
  const [result, setResult] = useState<AgentRun | null>(null);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const stop = useRef<() => void>(() => {});
  useEffect(() => () => stop.current(), []);

  // From the landing page: /agent?goal=...&run=1 fills the box and starts once (not again on reload).
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const g = q.get("goal")?.slice(0, 600) ?? "";
    if (!g) return;
    setGoal(g);
    if (q.get("run") === "1" && g.trim().length >= 10) {
      history.replaceState(null, "", `/agent?goal=${encodeURIComponent(g)}`);
      void start(g);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function start(text = goal) {
    stop.current();
    setSteps([]);
    setCalls({ live: 0, cached: 0 });
    setResult(null);
    setError(null);
    setBusy(true);
    try {
      const { id } = await api.startAgent(text.trim());
      setRunId(id);
      stop.current = streamAgent(
        id,
        (ev) => {
          if (ev.type === "step") {
            setSteps((s) => [...s.filter((x) => x.n !== ev.data.n), { ...ev.data }]);
            play("tick");
          } else if (ev.type === "observation") {
            setSteps((s) => s.map((x) => (x.n === ev.data.n ? { ...x, obs: ev.data.text, ok: ev.data.ok } : x)));
            play(ev.data.ok ? "coin" : "back");
          } else if (ev.type === "qloo_call") {
            setCalls((c) => (ev.data.cache_hit ? { ...c, cached: c.cached + 1 } : { ...c, live: c.live + 1 }));
          } else if (ev.type === "done") {
            api
              .agent(id)
              .then((r) => {
                setResult(r);
                play("win");
              })
              .finally(() => setBusy(false));
          } else if (ev.type === "failed") {
            setError(ev.data);
            setBusy(false);
            play("error");
          }
        },
        () => {},
      );
    } catch (e) {
      const err = e as ApiError;
      setError({ code: err.code, message: err.message });
      setBusy(false);
      play("error");
    }
  }

  /** The LLM is down: carry the description into the form, where comp search needs only Qloo. */
  function planByHand() {
    try {
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ draft: { ...emptyDraft(), description: goal.trim() }, step: 0 }));
    } catch {
      /* storage blocked: the form opens empty */
    }
    router.push("/plan/new");
  }

  function openPlan() {
    const d = result?.draft;
    if (!d) return;
    const draft: Draft = {
      ...emptyDraft(),
      title: d.title === "Your game" ? "" : d.title,
      description: d.description,
      comps: d.games.map((g) => ({ entity_id: g.entity_id, name: g.name })),
      culture: d.culture,
      platforms: d.platforms,
      regions: d.regions,
    };
    try {
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ draft, step: draft.title ? 2 : 0 }));
    } catch {
      /* storage blocked: the form opens empty */
    }
    router.push("/plan/new");
  }

  const names = useMemo(() => handleNames(steps), [steps]);
  const ready = goal.trim().length >= 10;

  return (
    <div className="stack agent" style={{ paddingTop: 32 }}>
      <header className="stack">
        <span className="label muted">Launch agent</span>
        <h1 className="h1">Plan my launch</h1>
        <p className="lede" style={{ maxWidth: 780 }}>
          Describe your game and what you want to know. The agent decides which Qloo tools to use, step by step: it finds
          comparable games, ranks cities, checks partners and audiences, then answers using only what Qloo returned.
        </p>
      </header>

      <div className="field" style={{ maxWidth: 820 }}>
        <label className="label" htmlFor="goal">
          Your game and your question
        </label>
        <textarea
          id="goal"
          className="textarea"
          value={goal}
          maxLength={600}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="What the game is, its platforms, and what you want to decide."
        />
        <div className="row popular">
          <span className="label muted">Try</span>
          {EXAMPLES.map((x) => (
            <button key={x} type="button" className="chip-btn" onClick={() => setGoal(x)} title={x}>
              {x.split(".")[0]}
            </button>
          ))}
        </div>
      </div>
      <div className="row" style={{ alignItems: "center" }}>
        <button
          className={result?.draft ? "ghost" : "btn btn-lg"}
          data-sfx="select"
          onClick={() => start()}
          disabled={busy || !ready}
        >
          {busy ? "Agent at work…" : "Run the agent"}
        </button>
        {runId && (
          <span className="label muted num">
            Qloo calls: {calls.live} live / {calls.cached} cached
          </span>
        )}
      </div>

      {error &&
        (error.code.startsWith("llm_") ? (
          <Notice tone="warn">
            The agent&apos;s language model is unavailable right now. You can still build the plan yourself: comp search
            and every score come from Qloo.{" "}
            <button className="btn" data-sfx="confirm" onClick={planByHand}>
              Build the plan yourself
            </button>
          </Notice>
        ) : (
          <Notice tone="warn">{error.message}</Notice>
        ))}

      {steps.length > 0 && (
        <ol className="agent-steps" aria-live="polite">
          {steps.map((s) => (
            <li key={s.n} className={`agent-step ${s.ok === false ? "bad" : ""} ${s.obs === undefined ? "pending" : ""}`}>
              <span className="step-n num">{s.n}</span>
              <div className="stack" style={{ gap: 6 }}>
                <div className="row" style={{ alignItems: "center", gap: 8 }}>
                  <span className="tool-chip">{TOOL_LABEL[s.tool] ?? s.tool}</span>
                  <span className="hint">{argText(s.args, names)}</span>
                </div>
                {s.thought && <p className="thought">{s.thought}</p>}
                {s.obs === undefined ? (
                  <p className="obs pending-dots" aria-label="Waiting for Qloo">
                    Calling Qloo
                  </p>
                ) : (
                  <pre className="obs">{s.obs}</pre>
                )}
              </div>
            </li>
          ))}
          {busy && !result && (
            <li className="agent-step pending">
              <span className="step-n num">…</span>
              <p className="thought pending-dots">Thinking</p>
            </li>
          )}
        </ol>
      )}

      {result?.answer && (
        <section className="agent-answer stack">
          <span className="label">
            {result.answer_source === "llm" ? `Answer by ${result.model}, checked against Qloo` : "Answer from the Qloo ranking"}
          </span>
          <p className="lede" style={{ fontSize: 19 }}>
            <RichText text={result.answer} traceHref="#" />
          </p>
          <p className="hint">
            {result.steps.length} steps · {result.calls.live} live / {result.calls.cached} cached Qloo calls · names and
            numbers come only from tool results · affinity index, not a sales forecast.
          </p>
          {result.draft && (
            <div>
              <button className="btn btn-lg" data-sfx="confirm" onClick={openPlan}>
                Open as a launch plan
              </button>
              <span className="hint" style={{ marginLeft: 12 }}>
                Prefills {result.draft.games.length} comps
                {result.draft.culture.length ? `, ${result.draft.culture.length} culture anchors` : ""} and{" "}
                {result.draft.regions.length} cities.
              </span>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
