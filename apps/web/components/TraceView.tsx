"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { TraceRow } from "@repo/contracts";
import { api, ApiError } from "../lib/api";
import { STEPS } from "../lib/progress";
import { ErrorScreen, Skeleton } from "./ui";

export function TraceView({ id, initial, backHref }: { id: string; initial?: TraceRow[]; backHref: string }) {
  const [rows, setRows] = useState<TraceRow[] | null>(initial ?? null);
  const [error, setError] = useState<ApiError | null>(null);
  const [step, setStep] = useState("all");
  const [hl, setHl] = useState("");

  useEffect(() => {
    if (!initial) api.trace(id).then(setRows).catch(setError);
  }, [id, initial]);

  // Highlight and scroll to the row named in the URL hash (citation chips link here).
  useEffect(() => {
    const sync = () => {
      const h = decodeURIComponent(location.hash.slice(1));
      setHl(h);
      if (h) requestAnimationFrame(() => document.getElementById(h)?.scrollIntoView({ block: "center" }));
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, [rows]);

  if (error)
    return (
      <ErrorScreen
        code={error.code}
        title="Can't load the trace"
        message={error.message}
        action={<Link className="ghost" href={backHref}>Back to the plan</Link>}
      />
    );

  const steps = ["all", ...new Set((rows ?? []).map((r) => r.step))];
  const shown = (rows ?? []).filter((r) => step === "all" || r.step === step);
  const live = (rows ?? []).filter((r) => !r.cache_hit).length;

  return (
    <section className="stack" style={{ paddingTop: 32 }}>
      <div className="spread">
        <h1 className="h1">Qloo call trace</h1>
        <Link className="textlink" href={backHref}>
          Back to the plan
        </Link>
      </div>
      <p className="lede" style={{ maxWidth: 820 }}>
        Every number in the plan came from one of these calls. Citation chips like <span className="cite">q3</span> point
        here.
      </p>
      {rows && (
        <p className="label muted">
          {rows.length} calls · {live} live · {rows.length - live} cached · API key never recorded
        </p>
      )}
      <div className="row" role="group" aria-label="Filter by step">
        {steps.map((s) => (
          <button key={s} className="tab" aria-pressed={step === s} onClick={() => setStep(s)} style={{ border: "1px solid var(--ink)", borderRadius: 8 }}>
            {s === "all" ? "All steps" : `${s} · ${STEPS.find((x) => x.key === s)?.label ?? s}`}
          </button>
        ))}
      </div>
      {!rows ? (
        <Skeleton h={400} />
      ) : rows.length === 0 ? (
        <p className="hint">No Qloo calls were made for this plan (the run stopped before reaching Qloo).</p>
      ) : (
        <div className="table-wrap">
          <table className="trace">
            <thead>
              <tr>
                <th>Id</th>
                <th>Step</th>
                <th>Endpoint</th>
                <th>Parameters</th>
                <th>Cache</th>
                <th>Status</th>
                <th>ms</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r, i) => (
                <tr key={r.result_id} id={r.result_id} className={hl === r.result_id ? "hl" : ""} style={{ ["--i" as string]: i }}>
                  <td className="num">
                    <b>{r.result_id}</b>
                  </td>
                  <td className="label">{r.step}</td>
                  <td className="num">{r.endpoint}</td>
                  <td>
                    <details>
                      <summary className="hint" style={{ cursor: "pointer" }}>
                        {r.params["filter.type"] ?? r.params["query"] ?? `${Object.keys(r.params).length} params`}
                      </summary>
                      <pre className="num" style={{ fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-all", marginTop: 8 }}>
                        {Object.entries(r.params)
                          .map(([k, v]) => `${k}=${v}`)
                          .join("\n")}
                      </pre>
                    </details>
                  </td>
                  <td className="label">{r.cache_hit ? "hit" : "live"}</td>
                  <td className="num">{r.status}</td>
                  <td className="num">{r.duration_ms}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
