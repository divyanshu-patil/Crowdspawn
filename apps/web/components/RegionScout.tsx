"use client";

import { useEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent } from "react";
import Link from "next/link";
import type { AreaActivity, EntityOut, PlaceHit, PlatformMix, ScoutArea, ScoutJudge } from "@repo/contracts";
import { api, ApiError } from "../lib/api";
import { COUNTRIES, GRID, OWNER, type CountryShape } from "../lib/countries";
import snapshotJson from "../lib/scout-snapshot.json";
import { lift as fmt } from "../lib/format";
import { play } from "../lib/sfx";
import { PLATFORMS, type Platform } from "../lib/validate";
import { GameSearch } from "./NewPlanForm";
import { ConfidenceBadge, Notice, Skeleton } from "./ui";

const W = GRID.cols;
const H = GRID.rows;
const toXY = (lat: number, lon: number) => ({ x: (lon + 180) / GRID.step, y: (GRID.latTop - lat) / GRID.step });
const toLatLon = (x: number, y: number) => ({ lat: GRID.latTop - y * GRID.step, lon: x * GRID.step - 180 });

type CountryReading = { mix: PlatformMix; cities: string[] };

/** What the panel shows: a live scout, or a place from the bundled Qloo snapshot. */
type AreaView = Omit<ScoutArea, "games" | "calls"> & {
  games: { name: string; image_url?: string | null }[];
  calls?: ScoutArea["calls"];
  snapshot?: string;
};
type SnapArea = AreaView & { id: string; name: string; country: string };

// "What works here" for 50 popular places, generated from Qloo by apps/api/scripts/snapshot_scout.py.
const SNAPSHOT = snapshotJson as unknown as { generated: string; activity: AreaActivity[]; areas: SnapArea[] };
const POPULAR = ["New York", "London", "Tokyo", "Seoul", "Sao Paulo", "Mumbai", "Istanbul", "Jakarta", "Lagos", "Berlin"];

function snapshotNear(lat: number, lon: number): SnapArea | null {
  let best: SnapArea | null = null;
  let bestKm = 60; // close enough to be the same metro area
  for (const a of SNAPSHOT.areas) {
    const d = km({ lat, lon }, a);
    if (d < bestKm) [best, bestKm] = [a, d];
  }
  return best;
}

/** English country name at a coordinate, from the generated tile grid (nearest land tile for coasts). */
function countryAt(lat: number, lon: number): string | null {
  return countryShapeAt(lat, lon)?.name ?? null;
}

function countryShapeAt(lat: number, lon: number): CountryShape | null {
  const r0 = Math.floor((GRID.latTop - lat) / GRID.step);
  const c0 = Math.floor((lon + 180) / GRID.step);
  for (let ring = 0; ring <= 2; ring++)
    for (let dr = -ring; dr <= ring; dr++)
      for (let dc = -ring; dc <= ring; dc++) {
        if (Math.max(Math.abs(dr), Math.abs(dc)) !== ring) continue;
        const ch = OWNER[r0 + dr]?.[(c0 + dc + GRID.cols) % GRID.cols];
        if (ch && ch !== ".") return COUNTRIES[ch.charCodeAt(0) - 48] ?? null;
      }
  return null;
}

/** "Mumbai, India": the place, then its country in plain English. */
const placeTitle = (h: PlaceHit) => [h.name, countryAt(h.lat, h.lon)].filter(Boolean).join(", ");
type Pick = { lat: number; lon: number; label: string; country?: string };

/** Mean of each platform over a country's points. */
function byCountry(points: AreaActivity[]): Map<string, CountryReading> {
  const groups = new Map<string, AreaActivity[]>();
  points.forEach((p) => groups.set(p.country, [...(groups.get(p.country) ?? []), p]));
  const avg = (ps: AreaActivity[], k: keyof PlatformMix) => ps.reduce((s, p) => s + p.mix[k], 0) / ps.length;
  return new Map(
    [...groups].map(([c, ps]) => [
      c,
      {
        mix: { pc: avg(ps, "pc"), mobile: avg(ps, "mobile"), console: avg(ps, "console"), general: avg(ps, "general") },
        cities: ps.map((p) => p.name),
      },
    ]),
  );
}

/** Five heat steps for the activity index; the legend shows the same cut points. */
const STEPS = [0.72, 0.78, 0.84, 0.88];
const heatStep = (g: number) => STEPS.filter((s) => g >= s).length;

/** Great-circle distance in km. */
function km(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
  const r = Math.PI / 180;
  const h =
    Math.sin(((b.lat - a.lat) * r) / 2) ** 2 +
    Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(((b.lon - a.lon) * r) / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(h));
}

export function RegionScout() {
  // Start from the bundled snapshot so the map is coloured at once; live readings replace it when they arrive.
  const [readings, setReadings] = useState<Map<string, CountryReading> | null>(() => byCountry(SNAPSHOT.activity));
  const [points, setPoints] = useState<AreaActivity[]>(SNAPSHOT.activity);
  const [snapNote, setSnapNote] = useState<string | null>(null);
  const [activityError, setActivityError] = useState<string | null>(null);
  const [pick, setPick] = useState<Pick | null>(null);
  const [area, setArea] = useState<AreaView | null>(null);
  const [areaError, setAreaError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<"works" | "fit">("works");
  const [spot, setSpot] = useState<Spot | null>(null); // a popular place being hovered in the chip row

  useEffect(() => {
    api
      .activity()
      .then((a) => {
        setReadings(byCountry(a.points));
        setPoints(a.points);
      })
      .catch((e: ApiError) => setActivityError(`Showing the ${SNAPSHOT.generated} snapshot: ${e.message}`));
  }, []);

  async function scout(p: Pick, snapped = false) {
    const snap = snapshotNear(p.lat, p.lon);
    if (snap) {
      // Popular place: answer instantly from the bundled Qloo snapshot, no API call.
      const title = [snap.name, countryAt(snap.lat, snap.lon)].filter(Boolean).join(", ");
      setPick({ lat: snap.lat, lon: snap.lon, label: title });
      setArea({ ...snap, snapshot: SNAPSHOT.generated });
      setAreaError(null);
      setLoading(false);
      if (!snapped) setSnapNote(null);
      play("coin");
      return;
    }
    setPick(p);
    setArea(null);
    setAreaError(null);
    if (!snapped) setSnapNote(null);
    setLoading(true);
    play("select");
    try {
      setArea(await api.area(p.lat, p.lon));
      play("coin");
    } catch (e) {
      const err = e as ApiError;
      // Open country between towns: snap to the nearest city Qloo has a reading for.
      const near = [...points].sort((a, b) => km(p, a) - km(p, b))[0];
      if (err.code === "no_area_data" && !snapped && near && km(p, near) < 1500) {
        setSnapNote(`No Qloo data right there, so this is the nearest city with players: ${near.name}.`);
        return scout({ lat: near.lat, lon: near.lon, label: near.name }, true);
      }
      setAreaError(err.message);
      play("error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="stack scout" style={{ paddingTop: 32 }}>
      <header className="stack">
        <span className="label muted">Region scout</span>
        <h1 className="h1">Scout a region</h1>
        <p className="lede" style={{ maxWidth: 760 }}>
          Click anywhere on the map or search for a place. See what players there love, or test whether your game fits.
        </p>
        <PlaceSearch
          onPick={(h) => scout({ lat: h.lat, lon: h.lon, label: placeTitle(h) })}
        />
        <div className="row popular" aria-label="Popular places, instant from a Qloo snapshot">
          <span className="label muted">Popular</span>
          {POPULAR.map((n) => {
            const a = SNAPSHOT.areas.find((x) => x.name === n)!;
            return (
              <button
                key={n}
                type="button"
                className="chip-btn"
                onClick={() => scout({ lat: a.lat, lon: a.lon, label: n })}
                onPointerEnter={() => setSpot({ lat: a.lat, lon: a.lon, label: n })}
                onPointerLeave={() => setSpot(null)}
                onFocus={() => setSpot({ lat: a.lat, lon: a.lon, label: n })}
                onBlur={() => setSpot(null)}
              >
                {n}
              </button>
            );
          })}
        </div>
      </header>

      {activityError && <Notice tone="warn">{activityError}</Notice>}
      <RegionMap readings={readings} pick={pick} spot={spot} onPick={scout} />

      <section className="scout-panel" aria-live="polite" aria-busy={loading}>
        {!pick && (
          <p className="hint">
            Pick a spot to scout. Countries are shaded by how strongly people there match popular games in Qloo&apos;s taste
            data; hover one to see the PC, console and mobile scores (out of 100, not player counts).
          </p>
        )}
        {pick && (
          <div className="stack">
            <div className="spread">
              <h2 className="h2">
                <span className="marker">{pick.label}</span>
              </h2>
              <span className="label muted num">
                {pick.lat.toFixed(1)}°, {pick.lon.toFixed(1)}° · {area?.radius_km ?? 40} km radius
              </span>
            </div>
            <div className="tabs" role="tablist">
              {(
                [
                  ["works", "What works here"],
                  ["fit", "Will my game work here?"],
                ] as const
              ).map(([k, l]) => (
                <button key={k} role="tab" aria-selected={tab === k} className="tab" onClick={() => setTab(k)}>
                  {l}
                </button>
              ))}
            </div>
            {snapNote && <Notice>{snapNote}</Notice>}
            {loading && <Skeleton h={220} />}
            {areaError && <Notice tone="warn">{areaError}</Notice>}
            {area && tab === "works" && <WhatWorks area={area} />}
            {area && tab === "fit" && <Fit pick={pick} />}
          </div>
        )}
      </section>
    </div>
  );
}

function PlaceSearch({ onPick }: { onPick: (h: PlaceHit) => void }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<PlaceHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) return setHits(null);
    setBusy(true);
    const t = setTimeout(() => {
      api
        .places(term)
        .then((r) => {
          // The same town can come back several times (city, district, metro area): keep one per label.
          const seen = new Set<string>();
          setHits(r.filter((h) => !seen.has(placeTitle(h) + h.region) && seen.add(placeTitle(h) + h.region)));
          setError(null);
        })
        .catch((e: ApiError) => setError(e.message))
        .finally(() => setBusy(false));
    }, 350);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div className="field" style={{ maxWidth: 560, position: "relative" }}>
      <label className="sr-only" htmlFor="place-q">
        Search a town, city or region
      </label>
      <div className="pill">
        <input
          id="place-q"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search a place: Lagos, Kyiv, Sao Paulo…"
          autoComplete="off"
        />
        <span className="btn" aria-hidden style={{ pointerEvents: "none" }}>
          {busy ? "…" : "Find"}
        </span>
      </div>
      {error && <p className="err">{error}</p>}
      {hits && hits.length === 0 && !busy && <p className="hint">No Qloo place matches “{q}”.</p>}
      {hits && hits.length > 0 && (
        <ul className="place-hits">
          {hits.map((h, i) => (
            <li key={h.entity_id} style={{ ["--i" as string]: i }}>
              <button
                type="button"
                onClick={() => {
                  onPick(h);
                  setQ("");
                  setHits(null);
                }}
              >
                <b>{placeTitle(h)}</b>
                {h.region && <span className="muted"> · {h.region}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type View = { k: number; x: number; y: number };
const HOME: View = { k: 1, x: 0, y: 0 };
const MAX_K = 6;

type Spot = { lat: number; lon: number; label: string };

function RegionMap({
  readings,
  pick,
  spot,
  onPick,
}: {
  readings: Map<string, CountryReading> | null;
  pick: Pick | null;
  spot: Spot | null;
  onPick: (p: Pick) => void;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const fig = useRef<HTMLElement>(null);
  const [hover, setHover] = useState<{ c: CountryShape; x: number; y: number } | null>(null);
  const [view, setView] = useState<View>(HOME);
  const drag = useRef<{ x: number; y: number; v: View; moved: boolean } | null>(null);
  // Smooth camera: `goal` is where the view is heading, `cur` what is drawn; each frame closes part of the gap.
  const cur = useRef<View>(HOME);
  const goal = useRef<View>(HOME);
  const raf = useRef(0);

  const clamp = (v: View): View => {
    const k = Math.min(MAX_K, Math.max(1, v.k));
    const vw = W / k;
    const vh = H / k;
    return { k, x: Math.min(W - vw, Math.max(0, v.x)), y: Math.min(H - vh, Math.max(0, v.y)) };
  };
  const draw = (v: View) => {
    cur.current = v;
    setView(v);
  };
  const goTo = (v: View, instant = false) => {
    goal.current = clamp(v);
    if (instant || matchMedia("(prefers-reduced-motion: reduce)").matches) {
      cancelAnimationFrame(raf.current);
      raf.current = 0;
      return draw(goal.current);
    }
    if (raf.current) return;
    let last = performance.now();
    const step = (now: number) => {
      const a = 1 - Math.exp(-(now - last) / 110); // frame-rate independent easing
      last = now;
      const c = cur.current;
      const g = goal.current;
      // Interpolate the visible width (not k) so the zoom anchor stays exactly under the cursor.
      const cw = W / c.k;
      const w = cw + (W / g.k - cw) * a;
      const next = { k: W / w, x: c.x + (g.x - c.x) * a, y: c.y + (g.y - c.y) * a };
      const done = Math.abs(w - W / g.k) < 0.002 && Math.abs(next.x - g.x) < 0.002 && Math.abs(next.y - g.y) < 0.002;
      draw(done ? g : next);
      raf.current = done ? 0 : requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
  };
  useEffect(() => () => cancelAnimationFrame(raf.current), []);

  // Wheel and trackpad zoom. Native listener: React's wheel handler is passive and cannot stop page scroll.
  const zoomRef = useRef<(f: number, cx?: number, cy?: number) => void>(() => {});
  useEffect(() => {
    const el = svg.current!;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(el.getScreenCTM()!.inverse());
      const lines = e.deltaMode === 1 ? 16 : 1; // Firefox reports lines
      zoomRef.current(Math.exp(-e.deltaY * lines * 0.0022), p.x, p.y);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  /** Zoom by `factor` keeping map point (cx, cy) fixed on screen. Builds on the goal, so wheel ticks add up. */
  const zoomAt = (factor: number, cx?: number, cy?: number) => {
    const c = cur.current;
    const g = goal.current;
    const cw = W / c.k;
    const ch = H / c.k;
    const rx = cx === undefined ? 0.5 : (cx - c.x) / cw; // cursor position as a fraction of the screen
    const ry = cy === undefined ? 0.5 : (cy - c.y) / ch;
    const px = g.x + rx * (W / g.k);
    const py = g.y + ry * (H / g.k);
    const k = Math.min(MAX_K, Math.max(1, g.k * factor));
    goTo({ k, x: px - rx * (W / k), y: py - ry * (H / k) });
  };
  zoomRef.current = zoomAt;
  const svgPoint = (clientX: number, clientY: number) => {
    const m = svg.current!.getScreenCTM()!.inverse();
    const p = new DOMPoint(clientX, clientY).matrixTransform(m);
    return { x: p.x, y: p.y };
  };

  // Fly to a searched place.
  useEffect(() => {
    if (!pick) return;
    const { x, y } = toXY(pick.lat, pick.lon);
    const inView = x > view.x && x < view.x + W / view.k && y > view.y && y < view.y + H / view.k;
    if (!inView || view.k < 2) goTo({ k: 3, x: x - W / 6, y: y - H / 6 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pick]);

  const shapes = useMemo(
    () =>
      COUNTRIES.map((c) => {
        const r = c.a2 ? readings?.get(c.a2) : undefined;
        return { c, step: r ? heatStep(r.mix.general) : -1 };
      }),
    [readings],
  );

  const onDown = (e: RPointerEvent<SVGSVGElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, v: cur.current, moved: false };
  };
  const onMove = (e: RPointerEvent<SVGSVGElement>) => {
    const box = fig.current!.getBoundingClientRect();
    const target = (e.target as Element).closest<SVGGElement>("g.country");
    const c = target ? COUNTRIES.find((x) => x.id === target.dataset.id) : undefined;
    setHover(c ? { c, x: e.clientX - box.left, y: e.clientY - box.top } : null);
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < 5) return;
    if (!d.moved) svg.current!.setPointerCapture(e.pointerId);
    d.moved = true;
    const scale = W / d.v.k / svg.current!.getBoundingClientRect().width;
    goTo({ k: d.v.k, x: d.v.x - dx * scale, y: d.v.y - dy * scale }, true); // drag follows the hand exactly
  };
  const onUp = (e: RPointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    drag.current = null;
    if (!d || d.moved) return;
    const p = svgPoint(e.clientX, e.clientY);
    const { lat, lon } = toLatLon(p.x, p.y);
    const target = (e.target as Element).closest<SVGGElement>("g.country");
    const c = target ? COUNTRIES.find((x) => x.id === target.dataset.id) : undefined;
    if (!c) return play("back"); // sea
    onPick({ lat, lon, label: c.name, country: c.name });
  };

  // A hovered popular-place chip lifts its country too.
  const spotCountry = spot ? countryShapeAt(spot.lat, spot.lon) : null;
  const hoverId = hover?.c.id ?? spotCountry?.id;
  // The country layer only changes with readings or hover, never with the camera, so frames stay cheap.
  const countryLayer = useMemo(
    () =>
      shapes.map(({ c, step }) => (
          <g
            key={c.id}
            data-id={c.id}
            className={`country h${step}${hoverId === c.id ? " lit" : ""}`}
            style={{ ["--d" as string]: `${Math.round(c.cx * 6)}ms` }}
          >
            <path className="side" d={c.d} />
            <g className="top">
              <path className="fill" d={c.d} />
              <path className="border" d={c.b} vectorEffect="non-scaling-stroke" />
            </g>
          </g>
        )),
    [shapes, hoverId],
  );
  const hovered = hover?.c.a2 ? readings?.get(hover.c.a2) : undefined;
  const at = pick ? toXY(pick.lat, pick.lon) : null;
  const unit = 1 / view.k; // keep rings and borders a constant on-screen size

  return (
    <figure
      ref={fig}
      className="map region-map"
      aria-label="World map of gamer taste match; click a place to scout it"
      style={{ ["--side" as string]: `${0.42 / Math.sqrt(view.k)}px` }}
    >
      <svg
        ref={svg}
        viewBox={`${view.x} ${view.y} ${W / view.k} ${H / view.k}`}
        className="region-svg"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerLeave={() => {
          setHover(null);
          drag.current = null;
        }}
        role="img"
      >
        <defs>
          <pattern id="pix" width="1" height="1" patternUnits="userSpaceOnUse">
            <path d="M1 0V1H0" fill="none" stroke="var(--paper)" strokeWidth={0.14} />
          </pattern>
        </defs>
        <rect x={0} y={0} width={W} height={H} className="sea" />
        {countryLayer}
        <rect x={0} y={0} width={W} height={H} fill="url(#pix)" pointerEvents="none" />
        {SNAPSHOT.areas.map((a) => {
          const p = toXY(a.lat, a.lon);
          return <circle key={a.id} className="spot" cx={p.x} cy={p.y} r={0.32 * unit * 1.6} pointerEvents="none" />;
        })}
        {spot && (() => {
          const p = toXY(spot.lat, spot.lon);
          return (
            <g className="spot-hl" transform={`translate(${p.x} ${p.y})`} pointerEvents="none">
              <circle className="halo" r={2.6 * unit * 1.6} />
              <circle className="halo two" r={2.6 * unit * 1.6} />
              <circle className="core" r={0.75 * unit * 1.6} />
              <g transform={`scale(${unit})`}>
                <text x={0} y={-3.2} textAnchor="middle" className="spot-label">
                  {spot.label}
                </text>
              </g>
            </g>
          );
        })()}
        {at && (
          <g className="pick" transform={`translate(${at.x} ${at.y})`} pointerEvents="none">
            <circle className="aoe" r={2.2 * unit * 2} />
            <circle className="ring" r={3 * unit * 2} />
            <circle className="ring two" r={3 * unit * 2} />
            <path className="cross" d={`M${-4 * unit} 0h${8 * unit}M0 ${-4 * unit}v${8 * unit}`} vectorEffect="non-scaling-stroke" />
            <circle className="dot" r={0.7 * unit} />
          </g>
        )}
      </svg>

      <div className="map-zoom" role="group" aria-label="Map zoom">
        <button type="button" aria-label="Zoom in" onClick={() => zoomAt(1.6)} disabled={view.k >= MAX_K}>
          +
        </button>
        <button type="button" aria-label="Zoom out" onClick={() => zoomAt(1 / 1.6)} disabled={view.k <= 1}>
          −
        </button>
        <button type="button" aria-label="Reset map view" className="label" onClick={() => goTo(HOME)}>
          Reset
        </button>
      </div>

      {hover && (
        <div
          className="region-tip"
          style={{ left: hover.x, top: hover.y, ["--flip" as string]: hover.x > (fig.current?.clientWidth ?? 0) - 260 ? 1 : 0 }}
          role="status"
        >
          <b>{hover.c.name}</b>
          {hovered ? (
            <>
              <span className="label muted">Gamer taste match, out of 100</span>
              <MixBars mix={hovered.mix} />
              <span className="hint">
                How strongly people here match each platform&apos;s hit games in Qloo, read in{" "}
                {hovered.cities.length > 3
                  ? `${hovered.cities.slice(0, 3).join(", ")} and ${hovered.cities.length - 3} more cities`
                  : hovered.cities.join(", ")}
                . A taste score, not a player count.
              </span>
            </>
          ) : (
            <span className="hint">{readings ? "No reading yet. Click to scout it." : "Loading readings…"}</span>
          )}
        </div>
      )}

      <figcaption className="map-legend label muted">
        <span>Gamer taste match:</span>
        <i className="key h-1" aria-hidden /> <span>no reading</span>
        <span>· low</span>
        {[0, 1, 2, 3, 4].map((s) => (
          <i key={s} className={`key h${s}`} aria-hidden />
        ))}
        <span>high · drag, scroll to zoom, click to scout</span>
      </figcaption>
    </figure>
  );
}

function MixBars({ mix }: { mix: PlatformMix }) {
  const rows: [string, number][] = [
    ["PC", mix.pc],
    ["Console", mix.console],
    ["Mobile", mix.mobile],
  ];
  return (
    <div className="mix" aria-label="Taste match out of 100 for PC, console and mobile hit games">
      {rows.map(([k, v], i) => (
        <div key={k} className="mix-row" style={{ ["--i" as string]: i }}>
          <span className="label">{k}</span>
          <span className="power">
            <i style={{ ["--v" as string]: Math.max(0.04, (v - 0.4) / 0.6) }} />
          </span>
          <span className="num">{Math.round(v * 100)}</span>
        </div>
      ))}
    </div>
  );
}

function WhatWorks({ area }: { area: AreaView }) {
  const max = Math.max(...area.genres.map((g) => g.lift));
  return (
    <div className="works">
      <div className="stack">
        <h3 className="h3">Genres that over-index here</h3>
        <ol className="genres">
          {area.genres.map((g, i) => (
            <li key={g.genre} className={g.lift > 1 ? "hot" : ""} style={{ ["--i" as string]: i }}>
              <span className="g-name">
                <b>{g.genre}</b>
                <span className="hint">like {g.examples.join(", ")}</span>
              </span>
              <span className="power">
                <i style={{ ["--v" as string]: Math.max(0.04, (g.lift - 0.6) / (max - 0.6)) }} />
              </span>
              <span className="num">×{fmt(g.lift)}</span>
            </li>
          ))}
        </ol>
        <p className="hint">
          Each genre is a panel of 3-4 well-known games; ×1.10 means its fans show up here 10% more than gamers in general.
        </p>
      </div>
      <div className="stack">
        <h3 className="h3">Platform taste match</h3>
        <MixBars mix={area.mix} />
        <p className="hint">Out of 100: how strongly people here match each platform&apos;s hit games. Not a player count.</p>
        <h3 className="h3" style={{ marginTop: 24 }}>
          Games locals love
        </h3>
        <ol className="local-games">
          {area.games.map((g, i) => (
            <li key={g.name} style={{ ["--i" as string]: i }}>
              {g.image_url ? <img src={g.image_url} alt="" loading="lazy" /> : <span className="ph">{g.name[0]}</span>}
              <span>{g.name}</span>
              <span className="num muted">#{i + 1}</span>
            </li>
          ))}
        </ol>
        <p className="hint">
          {area.cells} Qloo heatmap cells ·{" "}
          {area.snapshot
            ? `instant from a Qloo snapshot taken ${area.snapshot}`
            : `${area.calls?.live ?? 0} live / ${area.calls?.cached ?? 0} cached calls`}{" "}
          · affinity index, not sales.
        </p>
      </div>
    </div>
  );
}

/** Verdict colours by rarity; the words themselves come from the API (JUDGE_TIERS in judge.py). */
const TONE: Record<string, string> = {
  Legendary: "legendary",
  Epic: "epic",
  Rare: "rare",
  Uncommon: "uncommon",
  Common: "common",
};

function Gauge({ p }: { p: number }) {
  const r = 52;
  const c = Math.PI * r; // half circle
  return (
    <svg className="gauge" viewBox="0 0 128 72" aria-hidden>
      <path d="M12 64a52 52 0 0 1 104 0" className="track" />
      <path d="M12 64a52 52 0 0 1 104 0" className="value" style={{ strokeDasharray: c, strokeDashoffset: c * (1 - p) }} />
    </svg>
  );
}

function Fit({ pick }: { pick: Pick }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [comps, setComps] = useState<EntityOut[]>([]);
  const [platforms, setPlatforms] = useState<Platform[]>(["pc", "console", "mobile"]);
  const [result, setResult] = useState<ScoutJudge | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setResult(null), [pick]);
  const ready = description.trim().length >= 10;

  async function judge() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await api.judge({
        lat: pick.lat,
        lon: pick.lon,
        title: title.trim(),
        description: description.trim(),
        platforms,
        comp_entity_ids: comps.map((c) => c.entity_id),
      });
      setResult(r);
      play(r.probability >= 0.58 ? "win" : r.probability >= 0.42 ? "level" : "error");
    } catch (e) {
      setError((e as ApiError).message);
      play("error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <p className="muted">
        Describe your game. An LLM picks comparable games and the culture it draws on; Qloo checks every name and scores
        this spot against 8 cities around the world.
      </p>
      <div className="judge-form">
        <div className="field">
          <label className="label" htmlFor="j-title">
            Game title (optional)
          </label>
          <input id="j-title" className="input" value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} placeholder="Your game's name" />
        </div>
        <div className="field">
          <label className="label" htmlFor="j-desc">
            Describe your game
          </label>
          <textarea
            id="j-desc"
            className="textarea"
            value={description}
            maxLength={600}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What players do, the genre and mood, and where it is set if it is a real place."
          />
          <span className="hint">{description.length}/600 · at least 10 characters</span>
        </div>
        <div className="row">
          {PLATFORMS.map((p) => {
            const on = platforms.includes(p.id);
            return (
              <label key={p.id} className={`toggle${on ? " on" : ""}`}>
                <input
                  type="checkbox"
                  className="sr-only"
                  checked={on}
                  onChange={() =>
                    setPlatforms(on ? (platforms.length > 1 ? platforms.filter((x) => x !== p.id) : platforms) : [...platforms, p.id])
                  }
                />
                {on ? "◆" : "◇"} {p.label}
              </label>
            );
          })}
        </div>
        <details className="more">
          <summary className="label">Name specific comparable games (optional)</summary>
          <GameSearch
            label="Search games like yours"
            exclude={comps.map((c) => c.entity_id)}
            disabled={comps.length >= 5}
            onPick={(e) => setComps([...comps, e])}
          />
          <div className="row">
            {comps.map((c) => (
              <span key={c.entity_id} className="chip">
                {c.name}
                <button aria-label={`Remove ${c.name}`} onClick={() => setComps(comps.filter((x) => x.entity_id !== c.entity_id))}>
                  ×
                </button>
              </span>
            ))}
          </div>
        </details>
        <div>
          <button className="btn btn-lg" data-sfx="select" onClick={judge} disabled={busy || !ready}>
            {busy ? "Scouting with Qloo…" : "Judge my game here"}
          </button>
        </div>
      </div>
      {busy && <Skeleton h={260} />}
      {error && <Notice tone="warn">{error}</Notice>}
      {result && <JudgeResult r={result} />}
    </div>
  );
}

function JudgeResult({ r }: { r: ScoutJudge }) {
  const pct = Math.round(r.probability * 100);
  const max = Math.max(...r.ranking.map((x) => x.score), 1.01);
  return (
    <div className="stack judge">
      <div className={`verdict v-${TONE[r.verdict] ?? "uncommon"}`}>
        <div className="verdict-head">
          <div>
            <span className="label">Verdict</span>
            <strong className="verdict-title">{r.verdict}</strong>
            <span className="hint">
              Estimated chance players here over-index for your game. A model estimate from taste data, not sales odds.
            </span>
          </div>
          <div className="gauge-wrap" aria-label={`${pct} percent`}>
            <Gauge p={r.probability} />
            <span className="num gauge-num">{pct}%</span>
          </div>
        </div>
        <p className="breakdown num" aria-label="Spawn score breakdown">
          <span>
            <b>{fmt(r.lift)}</b> taste
          </span>
          ×
          <span>
            <b>{fmt(r.platform_fit)}</b> platform
          </span>
          {r.culture_fit != null && (
            <>
              ×
              <span>
                <b>{fmt(r.culture_fit)}</b> culture
              </span>
            </>
          )}
          =<span className="total">{fmt(r.score)}</span>
          <ConfidenceBadge level={r.confidence} />
        </p>
      </div>

      <div className="judge-grid">
        <section className="stack">
          <h3 className="h3">Against the world</h3>
          <ol className="ranking">
            {r.ranking.map((x, i) => (
              <li key={x.name} className={x.here ? "here" : ""} style={{ ["--i" as string]: i }}>
                <span className="r-name">{x.here ? "This spot" : x.name}</span>
                <span className={`power ${x.here ? "hot" : ""}`}>
                  <i style={{ ["--v" as string]: Math.max(0.04, x.score / max) }} />
                </span>
                <span className="num">×{fmt(x.score)}</span>
              </li>
            ))}
          </ol>
          <h3 className="h3">What Qloo matched from your description</h3>
          <div className="row">
            {r.comps.map((c) => (
              <span key={c} className="chip" style={{ paddingRight: 14 }}>
                {c}
              </span>
            ))}
          </div>
          {r.culture.length > 0 && (
            <div className="row">
              <span className="label muted">Setting via</span>
              {r.culture.map((c) => (
                <span key={c} className="chip" style={{ paddingRight: 14 }}>
                  {c}
                </span>
              ))}
            </div>
          )}
          {r.dropped.length > 0 && <p className="hint">Not found in Qloo, left out: {r.dropped.join(", ")}.</p>}
        </section>
        <section className="stack">
          <h3 className="h3">Hottest genres here</h3>
          <ol className="genres">
            {r.genres.slice(0, 5).map((g, i) => (
              <li key={g.genre} className={g.lift > 1 ? "hot" : ""} style={{ ["--i" as string]: i }}>
                <span className="g-name">
                  <b>{g.genre}</b>
                </span>
                <span className="power">
                  <i style={{ ["--v" as string]: Math.max(0.04, (g.lift - 0.6) / 0.8) }} />
                </span>
                <span className="num">×{fmt(g.lift)}</span>
              </li>
            ))}
          </ol>
          <h3 className="h3">Local favourites</h3>
          <div className="row">
            {r.games.map((g) => (
              <span key={g.entity_id} className="chip" style={{ paddingRight: 14 }}>
                {g.name}
              </span>
            ))}
          </div>
        </section>
      </div>

      <div className="judge-summary">
        <span className="label muted">{r.summary_source === "llm" ? `Explained by ${r.model}` : "Summary (template)"}</span>
        <p>{r.summary}</p>
        <p className="hint">
          {r.cells} heatmap cells · {r.calls.live} live / {r.calls.cached} cached Qloo calls · every name and number above
          comes from Qloo.
        </p>
      </div>
    </div>
  );
}
