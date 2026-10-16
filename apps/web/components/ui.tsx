"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Confidence } from "@repo/contracts";

export const CONFIDENCE_HELP =
  "High: at least 150 Qloo heatmap cells and spawn score at least 0.10 away from 1. " +
  "Medium: at least 50 cells and spawn score at least 0.03 away from 1. Low: anything else.";

export function ConfidenceBadge({ level }: { level: Confidence }) {
  const on = level === "high" ? 3 : level === "medium" ? 2 : 1;
  return (
    <span className="conf" title={CONFIDENCE_HELP}>
      <span className="pips" aria-hidden>
        {[0, 1, 2].map((i) => (
          <i key={i} className={i < on ? "on" : ""} />
        ))}
      </span>
      <span className="label">{level}</span>
      <span className="sr-only">confidence</span>
    </span>
  );
}

/** Citation chip that jumps to the matching Qloo trace row. */
export function Cite({ id, traceHref }: { id: string; traceHref: string }) {
  return (
    <a className="cite" href={`${traceHref}#${id}`} aria-label={`Qloo call ${id} in the trace`}>
      {id}
    </a>
  );
}

/** Counts up from the previous value; respects reduced motion. */
export function CountUp({ value, format = (n) => String(Math.round(n)) }: { value: number; format?: (n: number) => string }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = from.current;
    if (start === value || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      from.current = value;
      setShown(value);
      return;
    }
    const t0 = performance.now();
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / 700);
      const eased = 1 - Math.pow(1 - k, 3);
      setShown(start + (value - start) * eased);
      if (k < 1) raf = requestAnimationFrame(step);
      else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <span className="num">{format(shown)}</span>;
}

export function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="stat">
      <span className="label muted">{label}</span>
      <b>{children}</b>
    </div>
  );
}

export function Skeleton({ h = 120, w = "100%" }: { h?: number; w?: string | number }) {
  return <div className="skeleton" style={{ height: h, width: w }} aria-hidden />;
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn"; children: ReactNode }) {
  return (
    <div className={`notice ${tone === "warn" ? "warn" : ""}`} role={tone === "warn" ? "alert" : "status"}>
      <span className="label">{tone === "warn" ? "Heads up" : "Note"}</span>
      <div>{children}</div>
    </div>
  );
}

export function ErrorScreen({
  code,
  title,
  message,
  action,
}: {
  code: string;
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="err-screen" role="alert">
      <span className="code label">{code}</span>
      <h1 className="h1 glitch">{title}</h1>
      <p className="lede" style={{ marginTop: 20, fontSize: 21 }}>
        {message}
      </p>
      {action && <div className="row" style={{ marginTop: 28 }}>{action}</div>}
    </div>
  );
}

/** Render brief text: **Name** becomes a highlighted name, [q1, q2] become trace chips. */
export function RichText({ text, traceHref }: { text: string; traceHref: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\[q\d+(?:\s*,\s*q\d+)*\])/g);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("**") && p.endsWith("**")) return <strong key={i}>{p.slice(2, -2)}</strong>;
        if (/^\[q\d+/.test(p))
          return (
            <span key={i}>
              {p
                .slice(1, -1)
                .split(",")
                .map((id) => (
                  <Cite key={id} id={id.trim()} traceHref={traceHref} />
                ))}
            </span>
          );
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}
