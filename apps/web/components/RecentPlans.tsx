"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { forgetPlan, recentPlans, type RecentPlan } from "../lib/recent";

export function RecentPlans() {
  const [list, setList] = useState<RecentPlan[] | null>(null);
  useEffect(() => setList(recentPlans()), []);
  if (list === null) return null;
  return (
    <section className="stack" style={{ paddingTop: 32 }} aria-labelledby="recent-h">
      <h1 id="recent-h" className="h1">
        <span className="marker">Recent launches</span>
      </h1>
      <p className="lede">Launch plans you opened in this browser. They are saved on this device only.</p>
      {list.length === 0 ? (
        <p className="hint">
          No plans yet.{" "}
          <Link className="textlink" href="/agent">
            Plan your first launch
          </Link>{" "}
          or open the{" "}
          <Link className="textlink" href="/sample">
            sample plan
          </Link>
          .
        </p>
      ) : (
        <ul className="recent">
          {list.map((r) => (
            <li key={r.id} className="card recent-row">
              <Link href={`/plan/${r.id}`} className="recent-main">
                <b className="h3">{r.title}</b>
                <span className="hint">
                  {r.status === "done"
                    ? `Top spawn point: ${r.top ?? "–"} · ${r.cities} cities`
                    : r.status === "failed"
                      ? "Failed"
                      : "Still running"}
                </span>
              </Link>
              <span className="label muted">{r.created_at.slice(0, 10)}</span>
              <button
                className="ghost"
                aria-label={`Remove ${r.title} from this list`}
                onClick={() => {
                  forgetPlan(r.id);
                  setList(recentPlans());
                }}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
