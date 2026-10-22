"use client";

import { useEffect, useRef, useState } from "react";
import type { AskOut } from "@repo/contracts";
import { ApiError } from "../lib/api";
import { AiIcon, RichText } from "./ui";

type Msg = { who: "you" | "bot"; text: string; withheld?: boolean };

/** Ask AI: answers come only from the Qloo data on screen, grounding-checked on the server like the brief. */
export function AskAI({
  title,
  note,
  starters,
  ask,
  traceHref = "",
}: {
  title: string;
  note: string;
  starters: string[];
  ask: (question: string) => Promise<AskOut>;
  traceHref?: string;
}) {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const log = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [msgs, busy]);

  async function send(question: string) {
    const text = question.trim();
    if (text.length < 2 || busy) return;
    setQ("");
    setMsgs((m) => [...m, { who: "you", text }]);
    setBusy(true);
    try {
      const out = await ask(text);
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
        <AiIcon /> {title}
      </button>
    );
  return (
    <aside className="card chat no-print" aria-label={title}>
      <div className="spread">
        <span className="label row" style={{ gap: 6 }}>
          <AiIcon size={16} /> {title}
        </span>
        <button className="ghost" onClick={() => setOpen(false)} aria-label="Close chat">
          ✕
        </button>
      </div>
      <p className="hint">{note}</p>
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
        {busy && <p className="chat-msg bot hint">Reading the data…</p>}
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
          placeholder="Ask in your own words"
          aria-label="Your question"
        />
        <button className="btn" disabled={busy || q.trim().length < 2}>
          Ask
        </button>
      </form>
    </aside>
  );
}
