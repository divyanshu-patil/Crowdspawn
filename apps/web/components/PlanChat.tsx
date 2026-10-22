"use client";

import { useEffect, useRef, useState } from "react";
import type { Plan } from "@repo/contracts";
import { api, ApiError } from "../lib/api";
import { RichText } from "./ui";

type Msg = { who: "you" | "bot"; text: string; withheld?: boolean };

/** Ask this plan: answers come only from the plan's Qloo facts, grounding-checked on the server like the brief. */
export function PlanChat({ plan, traceHref }: { plan: Plan; traceHref: string }) {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const log = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [msgs, busy]);

  const top = plan.cities[0]?.name;
  const starters = [
    top && `Why is ${top} the top spawn point?`,
    "Which partner type should I market through first?",
    plan.audience && "Who is my audience?",
    plan.input.budget_usd != null && "How should I split the budget?",
  ].filter((s): s is string => !!s);

  async function send(question: string) {
    const text = question.trim();
    if (text.length < 2 || busy) return;
    setQ("");
    setMsgs((m) => [...m, { who: "you", text }]);
    setBusy(true);
    try {
      const out = await api.ask(plan, text);
      setMsgs((m) => [...m, { who: "bot", text: out.answer, withheld: !out.grounded }]);
    } catch (e) {
      setMsgs((m) => [...m, { who: "bot", text: e instanceof ApiError ? e.message : "Couldn't reach the API.", withheld: true }]);
    } finally {
      setBusy(false);
    }
  }

  if (!open)
    return (
      <button className="btn chat-fab no-print" onClick={() => setOpen(true)} data-testid="chat-open">
        Ask this plan
      </button>
    );
  return (
    <aside className="card chat no-print" aria-label="Ask this plan">
      <div className="spread">
        <span className="label">Ask this plan</span>
        <button className="ghost" onClick={() => setOpen(false)} aria-label="Close chat">
          ✕
        </button>
      </div>
      <p className="hint">Answers use only this plan&apos;s Qloo data, with citations. No outside knowledge, no forecasts.</p>
      <div className="chat-log" aria-live="polite" ref={log}>
        {msgs.length === 0 && (
          <div className="row">
            {starters.map((s) => (
              <button key={s} className="chip-btn" onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {msgs.map((m, i) => (
          <p key={i} className={`chat-msg ${m.who} ${m.withheld ? "withheld" : ""}`}>
            {m.who === "bot" ? <RichText text={m.text} traceHref={traceHref} /> : m.text}
          </p>
        ))}
        {busy && <p className="chat-msg bot hint">Reading the plan…</p>}
      </div>
      <form
        className="chat-form"
        onSubmit={(e) => {
          e.preventDefault();
          send(q);
        }}
      >
        <input
          className="input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          maxLength={300}
          placeholder="e.g. Which podcasts stand out?"
          aria-label="Your question"
        />
        <button className="btn" disabled={busy || q.trim().length < 2}>
          Ask
        </button>
      </form>
    </aside>
  );
}
