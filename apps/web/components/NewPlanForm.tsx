"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { EntityOut, Region } from "@repo/contracts";
import { api, ApiError } from "../lib/api";
import {
  emptyDraft,
  isValid,
  LIMITS,
  PLATFORMS,
  toPlanIn,
  validateAll,
  validateComps,
  validateGame,
  validateRegions,
  type Draft,
} from "../lib/validate";
import { Notice, Skeleton } from "./ui";

const KEY = "crowdspawn:draft";
const LEVELS = ["Your game", "Rivals", "Spawn zones"];

function useDraft(): [Draft, (d: Draft) => void, number, (s: number) => void] {
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [step, setStep] = useState(0);
  const loaded = useRef(false);
  useEffect(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(KEY) ?? "null");
      if (saved) {
        setDraft({ ...emptyDraft(), ...saved.draft });
        setStep(saved.step ?? 0);
      }
    } catch {
      /* storage unavailable: start fresh */
    }
    loaded.current = true;
  }, []);
  useEffect(() => {
    if (!loaded.current) return;
    try {
      sessionStorage.setItem(KEY, JSON.stringify({ draft, step }));
    } catch {
      /* ignore */
    }
  }, [draft, step]);
  return [draft, setDraft, step, setStep];
}

export function NewPlanForm() {
  const router = useRouter();
  const [draft, setDraft, step, setStep] = useDraft();
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const stepErrors = [validateGame, validateComps, validateRegions][step]!(draft);
  const allErrors = validateAll(draft);
  const set = (patch: Partial<Draft>) => setDraft({ ...draft, ...patch });

  function next() {
    setTouched(true);
    if (!isValid(stepErrors)) return;
    setTouched(false);
    setStep(step + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function submit() {
    setTouched(true);
    if (!isValid(allErrors)) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const { id } = await api.createPlan(toPlanIn(draft));
      sessionStorage.removeItem(KEY);
      router.push(`/plan/${id}`);
    } catch (e) {
      setSubmitError((e as ApiError).message);
      setSubmitting(false);
    }
  }

  const show = (k: keyof typeof stepErrors) => touched && stepErrors[k] && <p className="err">{stepErrors[k]}</p>;

  return (
    <div className="stack" style={{ paddingTop: 32, maxWidth: 920 }}>
      <div className="stack">
        <span className="label muted">
          Level {step + 1} of 3 · {LEVELS[step]}
        </span>
        <h1 className="h1">
          {step === 0 && "What are you launching?"}
          {step === 1 && "Who are your rivals?"}
          {step === 2 && "Where could your players spawn?"}
        </h1>
        <div className="xp" role="progressbar" aria-valuenow={step + 1} aria-valuemin={1} aria-valuemax={3} aria-label="Form progress">
          <i style={{ ["--v" as string]: (step + 1) / 3 }} />
        </div>
        <ol className="row" aria-label="Steps">
          {LEVELS.map((l, i) => (
            <li key={l} style={{ listStyle: "none" }}>
              <button
                className="textlink"
                disabled={i > step}
                aria-current={i === step ? "step" : undefined}
                onClick={() => i < step && setStep(i)}
                style={{ opacity: i > step ? 0.4 : 1, textDecoration: i === step ? "underline" : "none" }}
              >
                {i < step ? "✓ " : ""}
                {l}
              </button>
            </li>
          ))}
        </ol>
      </div>

      <div key={step} className="stack" style={{ animation: "rise 380ms var(--ease-out)" }}>
        {step === 0 && (
          <>
            <div className="field">
              <label className="label" htmlFor="title">
                Game title
              </label>
              <input
                id="title"
                className="input"
                value={draft.title}
                maxLength={LIMITS.titleMax + 20}
                onChange={(e) => set({ title: e.target.value })}
                placeholder="Ember Crypt"
                autoFocus
              />
              <span className="hint">
                {draft.title.length}/{LIMITS.titleMax}
              </span>
              {show("title")}
            </div>
            <div className="field">
              <label className="label" htmlFor="desc">
                Short description
              </label>
              <textarea
                id="desc"
                className="textarea"
                value={draft.description}
                onChange={(e) => set({ description: e.target.value })}
                placeholder="A fast roguelike dungeon crawler with hand-drawn bosses."
              />
              <span className="hint">
                {draft.description.length}/{LIMITS.descriptionMax}. Used only to suggest comps and culture; never sent to Qloo.
              </span>
              {show("description")}
            </div>
            <TagInput tags={draft.tags} onChange={(tags) => set({ tags })} />
            {show("tags")}
            <fieldset className="field" style={{ border: 0 }}>
              <legend className="label" style={{ marginBottom: 8 }}>
                Platforms
              </legend>
              <div className="row">
                {PLATFORMS.map((p) => {
                  const on = draft.platforms.includes(p.id);
                  return (
                    <label key={p.id} className={`toggle${on ? " on" : ""}`}>
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={on}
                        onChange={() =>
                          set({
                            platforms: on ? draft.platforms.filter((x) => x !== p.id) : [...draft.platforms, p.id],
                          })
                        }
                      />
                      {on ? "◆" : "◇"} {p.label}
                    </label>
                  );
                })}
              </div>
              <span className="hint">
                Markets differ by platform: console games do worse where people mostly play on PC or mobile.
              </span>
              {touched && validateComps(draft).platforms && <p className="err">{validateComps(draft).platforms}</p>}
            </fieldset>
          </>
        )}

        {step === 1 && (
          <>
            <CompsStep draft={draft} set={set} error={touched ? stepErrors.comps : undefined} />
            <CultureStep draft={draft} set={set} error={touched ? stepErrors.culture : undefined} />
          </>
        )}

        {step === 2 && (
          <RegionsStep draft={draft} set={set} errors={touched ? stepErrors : {}} />
        )}
      </div>

      {submitError && <Notice tone="warn">{submitError}</Notice>}

      <div className="row" style={{ justifyContent: "space-between", marginTop: 40 }}>
        <button className="textlink" onClick={() => setStep(step - 1)} style={{ visibility: step ? "visible" : "hidden" }}>
          Back
        </button>
        {step < 2 ? (
          <button className="ghost" onClick={next} disabled={touched && !isValid(stepErrors)}>
            Next level
          </button>
        ) : (
          <button className="btn btn-lg" onClick={submit} disabled={submitting || (touched && !isValid(allErrors))}>
            {submitting ? "Spawning…" : "Build launch plan"}
          </button>
        )}
      </div>
    </div>
  );
}

function TagInput({ tags, onChange }: { tags: string[]; onChange: (t: string[]) => void }) {
  const [text, setText] = useState("");
  const add = () => {
    const t = text.trim().replace(/,$/, "");
    if (t && !tags.includes(t) && tags.length < LIMITS.tagsMax) onChange([...tags, t]);
    setText("");
  };
  return (
    <div className="field">
      <label className="label" htmlFor="tags">
        Genre tags
      </label>
      <div className="row">
        {tags.map((t) => (
          <span key={t} className="chip">
            {t}
            <button aria-label={`Remove ${t}`} onClick={() => onChange(tags.filter((x) => x !== t))}>
              ×
            </button>
          </span>
        ))}
      </div>
      <input
        id="tags"
        className="input"
        value={text}
        placeholder={tags.length >= LIMITS.tagsMax ? "Tag limit reached" : "roguelike, pixel art… press Enter"}
        disabled={tags.length >= LIMITS.tagsMax}
        onChange={(e) => (e.target.value.endsWith(",") ? (setText(e.target.value), add()) : setText(e.target.value))}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            add();
          }
        }}
        onBlur={add}
      />
      <span className="hint">
        {tags.length}/{LIMITS.tagsMax} tags
      </span>
    </div>
  );
}

const TYPE_LABEL: Record<string, string> = {
  "urn:entity:movie": "Film",
  "urn:entity:tv_show": "Show",
  "urn:entity:artist": "Artist",
};

/** Debounced Qloo search through the API (games by default, or films, shows and artists). */
function GameSearch({
  label,
  onPick,
  exclude,
  disabled,
  search = api.search,
  noun = "video games",
}: {
  label: string;
  onPick: (e: EntityOut) => void;
  exclude: string[];
  disabled?: boolean;
  search?: (q: string) => Promise<EntityOut[]>;
  noun?: string;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<EntityOut[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setResults(null);
      return;
    }
    setLoading(true);
    const t = setTimeout(() => {
      search(term)
        .then((r) => {
          setResults(r);
          setError(null);
        })
        .catch((e: ApiError) => setError(e.message))
        .finally(() => setLoading(false));
    }, 350);
    return () => clearTimeout(t);
  }, [q, search]);

  const shown = (results ?? []).filter((r) => !exclude.includes(r.entity_id));
  return (
    <div className="field">
      <label className="sr-only" htmlFor={`search-${label}`}>
        {label}
      </label>
      <div className="pill">
        <input
          id={`search-${label}`}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={disabled ? "Slots full" : label}
          disabled={disabled}
          autoComplete="off"
        />
        <span className="btn" aria-hidden style={{ pointerEvents: "none" }}>
          {loading ? "…" : "Search"}
        </span>
      </div>
      {error && <p className="err">{error}</p>}
      {q.trim().length > 0 && q.trim().length < 2 && <p className="hint">Type at least two letters.</p>}
      {results && shown.length === 0 && !loading && (
        <p className="hint">
          No Qloo {noun} match “{q}”. Try the official title.
        </p>
      )}
      {shown.length > 0 && (
        <ul className="row" style={{ listStyle: "none", marginTop: 8 }}>
          {shown.map((r, i) => (
            <li key={r.entity_id} style={{ animation: `rise 300ms ${i * 40}ms var(--ease-out) both` }}>
              <button
                className="ghost"
                onClick={() => {
                  onPick(r);
                  setQ("");
                  setResults(null);
                }}
              >
                + {r.name}
                {r.year ? ` (${r.year})` : ""}
                {TYPE_LABEL[r.type] ? ` · ${TYPE_LABEL[r.type]}` : ""}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CompsStep({ draft, set, error }: { draft: Draft; set: (p: Partial<Draft>) => void; error?: string }) {
  const [suggesting, setSuggesting] = useState(false);
  const [dropped, setDropped] = useState<string[]>([]);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const full = draft.comps.length >= LIMITS.compsMax;

  async function suggest() {
    setSuggesting(true);
    setSuggestError(null);
    try {
      const r = await api.suggest({ title: draft.title, description: draft.description, tags: draft.tags });
      const have = new Set(draft.comps.map((c) => c.entity_id));
      const add = r.suggestions
        .map((s) => s.resolved!)
        .filter((e) => !have.has(e.entity_id))
        .slice(0, LIMITS.compsMax - draft.comps.length);
      set({ comps: [...draft.comps, ...add] });
      setDropped(r.dropped);
    } catch (e) {
      setSuggestError((e as ApiError).message);
    } finally {
      setSuggesting(false);
    }
  }

  return (
    <>
      <p className="lede" style={{ fontSize: 21 }}>
        Pick 1 to 5 released games your players already love. New indie games are rarely in Qloo yet, so the plan works
        through these.
      </p>
      <GameSearch
        label="Search Qloo games"
        exclude={draft.comps.map((c) => c.entity_id)}
        disabled={full}
        onPick={(e) => set({ comps: [...draft.comps, e] })}
      />
      <div className="row">
        <button className="ghost" onClick={suggest} disabled={suggesting || full || !draft.title.trim()}>
          {suggesting ? "Asking the oracle…" : "Suggest for me"}
        </button>
        <span className="hint">An LLM suggests names; only games Qloo can find are kept.</span>
      </div>
      {suggestError && <Notice tone="warn">{suggestError}</Notice>}
      {dropped.length > 0 && (
        <Notice>Not found in Qloo, so left out: {dropped.join(", ")}.</Notice>
      )}
      <div className="scatter" aria-live="polite">
        {draft.comps.length === 0 && <p className="hint">No comps yet. Search above or let us suggest some.</p>}
        {draft.comps.map((c, i) => (
          <figure
            key={c.entity_id}
            className="polaroid"
            style={{ ["--r" as string]: `${[-3, 2, -1.5, 3, -2][i]}deg`, ["--i" as string]: 0, ["--w" as string]: "160px" }}
          >
            {c.image_url ? <img src={c.image_url} alt="" /> : <div className="ph">{c.name[0]}</div>}
            <figcaption className="spread">
              <b>{c.name}</b>
              <button
                className="textlink"
                aria-label={`Remove ${c.name}`}
                onClick={() => set({ comps: draft.comps.filter((x) => x.entity_id !== c.entity_id) })}
              >
                ×
              </button>
            </figcaption>
          </figure>
        ))}
      </div>
      <span className="hint">
        {draft.comps.length}/{LIMITS.compsMax} comps
      </span>
      {error && <p className="err">{error}</p>}
    </>
  );
}

function CultureStep({ draft, set, error }: { draft: Draft; set: (p: Partial<Draft>) => void; error?: string }) {
  const [suggesting, setSuggesting] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const full = draft.culture.length >= LIMITS.cultureMax;

  async function suggest() {
    setSuggesting(true);
    setSuggestError(null);
    setNote(null);
    try {
      const r = await api.suggestCulture({ title: draft.title, description: draft.description, tags: draft.tags });
      const have = new Set(draft.culture.map((c) => c.entity_id));
      const add = r.suggestions
        .map((s) => s.resolved!)
        .filter((e) => !have.has(e.entity_id))
        .slice(0, LIMITS.cultureMax - draft.culture.length);
      set({ culture: [...draft.culture, ...add] });
      if (r.suggestions.length === 0)
        setNote("No real-world setting found in your description, so the plan will rank by taste alone.");
      else if (r.dropped.length) setNote(`Not found in Qloo, so left out: ${r.dropped.join(", ")}.`);
    } catch (e) {
      setSuggestError((e as ApiError).message);
    } finally {
      setSuggesting(false);
    }
  }

  return (
    <section className="stack" style={{ marginTop: 40 }} aria-labelledby="culture-h">
      <h2 className="h2" id="culture-h">
        Where is it set? <span className="muted">(optional)</span>
      </h2>
      <p className="lede" style={{ fontSize: 19 }}>
        If your game draws on a real place, add films, shows or artists people there love. Qloo finds where their fans
        live, so a game set in Delhi ranks Indian cities and the diaspora higher.
      </p>
      <GameSearch
        label="Search films, shows, artists"
        noun="films, shows or artists"
        search={api.searchCulture}
        exclude={draft.culture.map((c) => c.entity_id)}
        disabled={full}
        onPick={(e) => set({ culture: [...draft.culture, e] })}
      />
      <div className="row">
        <button className="ghost" onClick={suggest} disabled={suggesting || full || !draft.title.trim()}>
          {suggesting ? "Reading the setting…" : "Suggest from my description"}
        </button>
        <span className="hint">An LLM suggests names; only titles Qloo can find are kept.</span>
      </div>
      {suggestError && <Notice tone="warn">{suggestError}</Notice>}
      {note && <Notice>{note}</Notice>}
      <div className="row" aria-live="polite">
        {draft.culture.map((c) => (
          <span key={c.entity_id} className="chip">
            {c.name}
            <span className="muted"> · {TYPE_LABEL[c.type] ?? "Culture"}</span>
            <button
              aria-label={`Remove ${c.name}`}
              onClick={() => set({ culture: draft.culture.filter((x) => x.entity_id !== c.entity_id) })}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <span className="hint">
        {draft.culture.length}/{LIMITS.cultureMax} culture anchors
      </span>
      {error && <p className="err">{error}</p>}
    </section>
  );
}

function RegionsStep({
  draft,
  set,
  errors,
}: {
  draft: Draft;
  set: (p: Partial<Draft>) => void;
  errors: { regions?: string; budget?: string };
}) {
  const [regions, setRegions] = useState<Region[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .regions()
      .then((r) => {
        setRegions(r);
        if (draft.regions.length === 0) set({ regions: r.filter((x) => x.default).map((x) => x.id) });
      })
      .catch((e: ApiError) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selected = useMemo(() => new Set(draft.regions), [draft.regions]);
  const toggle = (id: string) =>
    set({ regions: selected.has(id) ? draft.regions.filter((r) => r !== id) : [...draft.regions, id] });

  return (
    <>
      <fieldset className="field" style={{ border: 0 }}>
        <legend className="label" style={{ marginBottom: 12 }}>
          Candidate cities ({draft.regions.length} of {LIMITS.regionsMin}–{LIMITS.regionsMax})
        </legend>
        {error && <Notice tone="warn">{error}</Notice>}
        {!regions && !error && <Skeleton h={160} />}
        <div className="row">
          {regions?.map((r, i) => (
            <label
              key={r.id}
              className="chip"
              style={{
                cursor: "pointer",
                paddingRight: 14,
                background: selected.has(r.id) ? "var(--ink)" : "var(--paper)",
                color: selected.has(r.id) ? "var(--paper)" : "var(--ink)",
                animationDelay: `${i * 30}ms`,
                transition: "background 160ms, color 160ms",
              }}
            >
              <input type="checkbox" className="sr-only" checked={selected.has(r.id)} onChange={() => toggle(r.id)} />
              {selected.has(r.id) ? "◆" : "◇"} {r.name}
            </label>
          ))}
        </div>
        {errors.regions && <p className="err">{errors.regions}</p>}
        <span className="hint">
          Each city costs up to 5 Qloo calls: your comps, PC, console and mobile player panels (shared and cached), and
          your culture anchors.
        </span>
      </fieldset>

      <div className="field" style={{ maxWidth: 320 }}>
        <label className="label" htmlFor="budget">
          Launch budget in USD (optional)
        </label>
        <input
          id="budget"
          className="input num"
          inputMode="decimal"
          value={draft.budget}
          onChange={(e) => set({ budget: e.target.value.replace(/[^0-9.]/g, "") })}
          placeholder="5000"
        />
        {errors.budget && <p className="err">{errors.budget}</p>}
      </div>

      <div className="field">
        <span className="label">Your previous game (optional)</span>
        <span className="hint">Adds a gap view: what your current players share with the target audience, and what&apos;s new.</span>
        <div className="row">
          {draft.previous.map((p) => (
            <span key={p.entity_id} className="chip">
              {p.name}
              <button
                aria-label={`Remove ${p.name}`}
                onClick={() => set({ previous: draft.previous.filter((x) => x.entity_id !== p.entity_id) })}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <GameSearch
          label="Search your previous game"
          exclude={[...draft.previous, ...draft.comps].map((x) => x.entity_id)}
          disabled={draft.previous.length >= 5}
          onPick={(e) => set({ previous: [...draft.previous, { entity_id: e.entity_id, name: e.name }] })}
        />
      </div>
    </>
  );
}
