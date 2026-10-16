"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

type Step = { path: string | null; target: string; title: string; body: string };

/** A guided walk through the app. Each step names a page and an element on it; `path: null` means any page. */
export const STEPS: Step[] = [
  {
    path: "/",
    target: ".hero",
    title: "Welcome to Crowdspawn",
    body: "Launch planning for indie games: where your players already are, and who else they love. Every number comes from Qloo taste data.",
  },
  {
    path: "/",
    target: "main > .section",
    title: "The spawn map",
    body: "A real plan for a Delhi-set crime game. Orange crowds are the cities where fans of games like it over-index: Mumbai, Delhi, Dubai.",
  },
  {
    path: "/sample",
    target: "section[aria-labelledby='cities-h']",
    title: "Cities, ranked",
    body: "Spawn score = taste lift × platform fit × culture fit, with confidence and a budget share. Above 1 means the city over-indexes.",
  },
  {
    path: "/sample",
    target: "section[aria-labelledby='partners-h']",
    title: "Allies to recruit",
    body: "Artists, podcasts, films and brands this audience loves, globally and in the top cities. These are your co-marketing leads.",
  },
  {
    path: "/sample",
    target: "section.brief",
    title: "A brief that can't make things up",
    body: "The LLM writes the words, but every name and number is checked against Qloo. Each chip opens the exact Qloo call behind it.",
  },
  {
    path: "/scout",
    target: ".region-map",
    title: "Scout any region",
    body: "Countries shaded by gamer taste match. Hover for PC, console and mobile readings, or click anywhere to see what works there.",
  },
  {
    path: "/scout",
    target: ".row.popular",
    title: "Popular places, instantly",
    body: "Hover a place to zoom to it, click to scout it. Then ask “Will my game work here?” for a Legendary-to-Common verdict.",
  },
  {
    path: "/agent",
    target: ".agent .field",
    title: "Or just ask the agent",
    body: "Describe your game and question. The agent picks Qloo tools step by step, shows its work, and hands its picks to a full plan.",
  },
  {
    path: null,
    target: ".nav a.btn[href='/plan/new']",
    title: "Plan your own launch",
    body: "Start with your game, a few comparable games and the culture it draws on. The plan streams in live.",
  },
];

const SEEN = "crowdspawn-tour-seen";
const PAD = 8;

export function Tour() {
  const router = useRouter();
  const pathname = usePathname();
  const [step, setStep] = useState<number | null>(null);
  const [offer, setOffer] = useState(false);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const card = useRef<HTMLDivElement>(null);

  // First visit to the landing page: offer the tour once.
  useEffect(() => {
    try {
      if (pathname === "/" && !localStorage.getItem(SEEN)) setOffer(true);
    } catch {
      /* storage blocked: no offer */
    }
  }, [pathname]);

  const remember = () => {
    try {
      localStorage.setItem(SEEN, "1");
    } catch {
      /* storage blocked */
    }
  };
  const start = () => {
    remember();
    setOffer(false);
    setStep(0);
  };
  const close = () => {
    remember();
    setOffer(false);
    setStep(null);
  };

  // Go to the step's page, wait for its element, bring it into view, then track it every frame.
  useEffect(() => {
    if (step === null) return;
    const s = STEPS[step]!;
    if (s.path && s.path !== pathname) {
      setRect(null);
      router.push(s.path);
      return;
    }
    let raf = 0;
    let scrolled = false;
    const t0 = performance.now();
    const tick = () => {
      const el = document.querySelector(s.target);
      if (el) {
        if (!scrolled) {
          const tall = el.getBoundingClientRect().height > innerHeight * 0.6;
          const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
          el.scrollIntoView({ block: tall ? "start" : "center", behavior: smooth ? "smooth" : "auto" });
          scrolled = true;
        }
        setRect(el.getBoundingClientRect());
      } else if (performance.now() - t0 > 4000) {
        setRect(null); // element never appeared: the card still explains the step
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    card.current?.focus();
    return () => cancelAnimationFrame(raf);
  }, [step, pathname, router]);

  useEffect(() => {
    if (step === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") setStep((n) => (n === null ? n : Math.min(n + 1, STEPS.length - 1)));
      else if (e.key === "ArrowLeft") setStep((n) => (n === null ? n : Math.max(n - 1, 0)));
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [step]);

  const s = step === null ? null : STEPS[step]!;
  const last = step === STEPS.length - 1;
  // Keep the card out of the way: top when the highlighted element sits low, bottom otherwise.
  const atTop = !!rect && rect.top + rect.height / 2 > innerHeight * 0.55;

  return (
    <>
      <button type="button" className="label tour-open" onClick={start}>
        Tour
      </button>

      {offer && step === null && (
        <div className="tour-card" role="dialog" aria-labelledby="tour-offer-h">
          <span className="label muted">New here?</span>
          <h2 id="tour-offer-h" className="h3">
            Take the one-minute tour
          </h2>
          <p>Nine stops: the spawn map, a full plan, the region scout and the launch agent.</p>
          <div className="row">
            <button type="button" className="btn" data-sfx="select" onClick={start}>
              Start the tour
            </button>
            <button type="button" className="ghost" data-sfx="back" onClick={close}>
              Not now
            </button>
          </div>
        </div>
      )}

      {s && (
        <>
          {rect && (
            <div
              className="tour-ring"
              aria-hidden
              style={{
                top: rect.top - PAD,
                left: rect.left - PAD,
                width: rect.width + PAD * 2,
                height: rect.height + PAD * 2,
              }}
            />
          )}
          <div
            ref={card}
            tabIndex={-1}
            className={`tour-card${atTop ? " top" : ""}`}
            role="dialog"
            aria-labelledby="tour-h"
            aria-describedby="tour-body"
          >
            <div className="spread">
              <span className="label muted num">
                Step {step! + 1} / {STEPS.length}
              </span>
              <button type="button" className="label textlink" data-sfx="back" onClick={close}>
                Skip tour
              </button>
            </div>
            <h2 id="tour-h" className="h3">
              {s.title}
            </h2>
            <p id="tour-body">{s.body}</p>
            <div className="row">
              <button
                type="button"
                className="ghost"
                data-sfx="back"
                disabled={step === 0}
                onClick={() => setStep(step! - 1)}
              >
                Back
              </button>
              <button
                type="button"
                className="btn"
                data-sfx={last ? "win" : "select"}
                onClick={() => (last ? close() : setStep(step! + 1))}
              >
                {last ? "Finish" : "Next"}
              </button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
