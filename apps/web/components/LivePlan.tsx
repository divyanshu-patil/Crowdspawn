"use client";

import { useEffect, useReducer, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { Plan, PlanEvent } from "@repo/contracts";
import { api, ApiError, streamPlan } from "../lib/api";
import { play } from "../lib/sfx";
import { initialProgress, reduce, STEPS, xp, type Progress } from "../lib/progress";
import { PlanView } from "./PlanView";
import { CountUp, ErrorScreen, Notice, Skeleton } from "./ui";

type Action = { kind: "event"; ev: PlanEvent & { id: number } } | { kind: "reset" };

function reducer(p: Progress, a: Action): Progress {
  return a.kind === "reset" ? initialProgress() : reduce(p, a.ev);
}

const FAILURE_COPY: Record<string, { title: string; message: string }> = {
  qloo_unconfigured: {
    title: "Qloo key missing",
    message: "The API has no QLOO_API_KEY, so no plan was made. Crowdspawn never invents data: add the key to apps/api/.env and retry.",
  },
  qloo_auth: {
    title: "Qloo rejected the key",
    message: "Qloo refused the API key, so no plan was made and no brief was written. Check QLOO_API_KEY and retry.",
  },
  qloo_budget_exceeded: {
    title: "Call budget spent",
    message: "This run hit the per-plan Qloo call cap, so partial results were discarded. Pick fewer cities and retry.",
  },
  qloo_daily_cap: {
    title: "Out of Qloo calls for today",
    message:
      "Today's live Qloo budget is used up. The sample plan and popular places still work. Try again after 00:00 UTC.",
  },
  comp_unresolved: {
    title: "No comps found",
    message: "None of the comparable games exist in Qloo. Go back and pick different comps.",
  },
};

export function LivePlan({ id }: { id: string }) {
  const router = useRouter();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [conn, setConn] = useState<"open" | "retrying">("open");
  const [progress, dispatch] = useReducer(reducer, undefined, initialProgress);
  const [retrying, setRetrying] = useState(false);

  // Load the plan; if it is still running, follow its SSE stream until done or failed.
  useEffect(() => {
    let stop = () => {};
    let cancelled = false;
    api
      .plan(id)
      .then((p) => {
        if (cancelled) return;
        if (p.status === "done") return setPlan(p);
        stop = streamPlan(
          id,
          (ev) => {
            dispatch({ kind: "event", ev });
            if (ev.type === "step_done") play("coin");
            if (ev.type === "failed") play("error");
            if (ev.type === "done") {
              play("win");
              api.plan(id).then((full) => !cancelled && setPlan(full));
            }
          },
          setConn,
        );
      })
      .catch((e: ApiError) => {
        if (cancelled) return;
        if (e.status === 404) setNotFound(true);
        else setLoadError(e);
      });
    return () => {
      cancelled = true;
      stop();
    };
  }, [id]);

  async function retry() {
    setRetrying(true);
    try {
      const p = await api.plan(id);
      const created = await api.createPlan(p.input);
      router.push(`/plan/${created.id}`);
    } catch (e) {
      setLoadError(e as ApiError);
      setRetrying(false);
    }
  }

  if (notFound)
    return (
      <ErrorScreen
        code="404 · plan_not_found"
        title="This save file is empty"
        message={`There is no plan with id “${id}”. It may have been made on another server.`}
        action={
          <>
            <Link className="btn" href="/agent">
              Plan my launch
            </Link>
            <Link className="ghost" href="/sample">
              See the sample
            </Link>
          </>
        }
      />
    );

  if (loadError)
    return (
      <ErrorScreen
        code={loadError.code}
        title="Can't load this plan"
        message={loadError.message}
        action={
          <button className="btn" onClick={() => location.reload()}>
            Try again
          </button>
        }
      />
    );

  if (progress.status === "failed" && progress.error) {
    const copy = FAILURE_COPY[progress.error.code] ?? {
      title: "Qloo didn't answer",
      message: `${progress.error.message}. No plan was made: Crowdspawn fails closed instead of guessing.`,
    };
    return (
      <ErrorScreen
        code={progress.error.code}
        title={copy.title}
        message={copy.message}
        action={
          <>
            <button className="btn" onClick={retry} disabled={retrying}>
              {retrying ? "Retrying…" : "Retry this plan"}
            </button>
            <Link className="ghost" href={`/plan/${id}/trace`}>
              See the calls that ran
            </Link>
          </>
        }
      />
    );
  }

  if (plan) return <PlanView plan={plan} traceHref={`/plan/${id}/trace`} />;

  return <QuestLog progress={progress} conn={conn} />;
}

export function QuestLog({ progress, conn }: { progress: Progress; conn: "open" | "retrying" }) {
  const v = xp(progress);
  const steps = STEPS.filter((s) => s.key !== "S6" || progress.hasGap);
  return (
    <section className="stack" style={{ paddingTop: 32 }} aria-live="polite" aria-busy="true">
      <div className="spread">
        <h1 className="h1">Building your launch plan</h1>
        <span className="row label">
          <span className={`live-dot ${conn === "open" ? "" : "off"}`} />
          {conn === "open" ? "Live from Qloo" : "Reconnecting…"}
        </span>
      </div>

      <div className="stack" style={{ maxWidth: 760 }}>
        <div className="spread">
          <span className="label">Quest progress</span>
          <span className="label num">{Math.round(v * 100)} / 100 XP</span>
        </div>
        <div className={`xp ${v >= 1 ? "done" : ""}`} role="progressbar" aria-valuenow={Math.round(v * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Plan progress">
          <i style={{ ["--v" as string]: v }} />
        </div>
      </div>

      <div className="two-col">
        <ol className="quest card">
          {steps.map((s) => {
            const st = progress.steps[s.key]!;
            return (
              <li key={s.key} className={st.status}>
                <span className="box" aria-hidden>
                  {st.status === "done" ? "✓" : ""}
                </span>
                <span>
                  <span className="q-name">{s.quest}</span>
                  <br />
                  <span className="hint">{st.summary ?? s.label}</span>
                </span>
                <span className="label muted">{s.key}</span>
              </li>
            );
          })}
        </ol>
        <div className="stack">
          <div className="hud">
            <div className="stat">
              <span className="label muted">Qloo calls</span>
              <b>
                <CountUp value={progress.calls.live + progress.calls.cached} />
              </b>
              <span className="hint">
                {progress.calls.live} live · {progress.calls.cached} from cache
              </span>
            </div>
          </div>
          {progress.lastCall && (
            <p className="label muted" key={progress.lastCall.result_id}>
              <span className="ticker">
                {progress.lastCall.result_id} → {progress.lastCall.endpoint}
                {progress.lastCall.cache_hit ? " (cache)" : ""}
              </span>
            </p>
          )}
          {progress.warnings
            .filter((w) => w.code !== "low_confidence_city")
            .map((w, i) => (
              <Notice key={i} tone="warn">
                {w.message}
              </Notice>
            ))}
          <Skeleton h={180} />
          <Skeleton h={90} />
        </div>
      </div>
    </section>
  );
}
