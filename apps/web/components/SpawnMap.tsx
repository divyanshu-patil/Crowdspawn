"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import type { City } from "@repo/contracts";
import { lift as fmtLift } from "../lib/format";
import { LAND, LAND_ROWS } from "../lib/land";

// Pixel overworld: one tile per LAND.step degrees, equirectangular.
const COLS = LAND_ROWS[0]!.length;
const ROWS = LAND_ROWS.length;
const W = 1000;
const CELL = W / COLS;
const H = Math.round(ROWS * CELL);
const TILE = Math.round((CELL - 1.2) * 100) / 100; // 1.2px gap keeps the tiles reading as pixels
const r2 = (n: number) => Math.round(n * 100) / 100; // identical strings on server and client

const isLand = (c: number, r: number) => LAND_ROWS[r]?.[c] === "1";
const colOf = (lon: number) => Math.floor((lon - LAND.lonLeft) / LAND.step);
const rowOf = (lat: number) => Math.floor((LAND.latTop - lat) / LAND.step);
const px = (lon: number) => r2(((lon - LAND.lonLeft) / LAND.step) * CELL);
const py = (lat: number) => r2(((LAND.latTop - lat) / LAND.step) * CELL);

// All land tiles as a single path: one DOM node instead of ~2,000 rects.
const LAND_PATH = LAND_ROWS.flatMap((row, r) =>
  [...row].flatMap((ch, c) => (ch === "1" ? [`M${r2(c * CELL)} ${r2(r * CELL)}h${TILE}v${TILE}h-${TILE}z`] : [])),
).join("");

/** Crowd size in tiles: one per 0.02 of spawn score above 1, capped. Under-indexing cities get one. */
export const crowdSize = (score: number) => Math.max(1, Math.min(24, Math.round((score - 1) / 0.02)));

/**
 * Light up the tiles nearest each city, land first. Cities claim tiles in rank order, so
 * neighbours (Tokyo/Seoul, the European cluster) never merge into one blob.
 */
function crowds(cities: City[]): Map<string, [number, number][]> {
  const claimed = new Set<string>();
  const out = new Map<string, [number, number][]>();
  for (const city of cities) {
    const c0 = colOf(city.lon);
    const r0 = rowOf(city.lat);
    const candidates: { c: number; r: number; d: number }[] = [];
    for (let dr = -6; dr <= 6; dr++)
      for (let dc = -6; dc <= 6; dc++) {
        const c = c0 + dc;
        const r = r0 + dr;
        if (r < 0 || r >= ROWS || c < 0 || c >= COLS || claimed.has(`${c},${r}`)) continue;
        candidates.push({ c, r, d: Math.hypot(dc, dr) + (isLand(c, r) ? 0 : 2.5) });
      }
    candidates.sort((a, b) => a.d - b.d || a.r - b.r || a.c - b.c);
    const picked = candidates.slice(0, crowdSize(city.score)).map(({ c, r }) => [c, r] as [number, number]);
    picked.forEach(([c, r]) => claimed.add(`${c},${r}`));
    out.set(city.region_id, picked);
  }
  return out;
}

const PIN_R = 7.5;
const PIN_R_TOP = 9.5;

/**
 * Nudge overlapping pins apart (deterministic relaxation). Each pin keeps a leader line back to
 * its true location, so dense regions (London/Paris, LA/SF) stay readable.
 */
function layoutPins(cities: City[], radius: (i: number) => number, gap: number) {
  const pos = cities.map((c) => ({ x: px(c.lon), y: py(c.lat) }));
  for (let iter = 0; iter < 60; iter++) {
    let moved = false;
    for (let i = 0; i < pos.length; i++)
      for (let j = i + 1; j < pos.length; j++) {
        const a = pos[i]!;
        const b = pos[j]!;
        const min = radius(i) + radius(j) + gap;
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let d = Math.hypot(dx, dy);
        if (d >= min) continue;
        if (d < 0.01) [dx, dy, d] = [1, 0, 1]; // identical points: split sideways
        const push = (min - d) / 2;
        a.x -= (dx / d) * push;
        a.y -= (dy / d) * push;
        b.x += (dx / d) * push;
        b.y += (dy / d) * push;
        moved = true;
      }
    if (!moved) break;
  }
  return pos.map((p) => ({ x: r2(p.x), y: r2(p.y) }));
}

type View = { x: number; y: number; k: number };
const MAX_K = 6;
const HOME: View = { x: 0, y: 0, k: 1 };
const wrapX = (x: number) => ((x % W) + W) % W; // the world repeats horizontally
const clampY = (y: number, k: number) => Math.min(Math.max(y, 0), H - H / k);
const norm = (v: View): View => ({ k: v.k, x: wrapX(v.x), y: clampY(v.y, v.k) });

/** Zoom to k2 keeping world point (cx, cy) under the same spot on screen. */
function zoomAt(v: View, k2: number, cx: number, cy: number): View {
  const k = Math.min(Math.max(k2, 1), MAX_K);
  const rx = (cx - v.x) / (W / v.k);
  const ry = (cy - v.y) / (H / v.k);
  return norm({ k, x: cx - (rx * W) / k, y: cy - (ry * H) / k });
}

export function SpawnMap({
  cities,
  activeId,
  onSelect,
}: {
  cities: City[];
  activeId?: string | null;
  onSelect?: (id: string) => void;
}) {
  const [view, setView] = useState<View>(HOME);
  const viewRef = useRef(view);
  viewRef.current = view;
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ id: number; px: number; py: number; v: View; moved: boolean } | null>(null);
  const justDragged = useRef(false);
  const tween = useRef(0);
  const goal = useRef<View>(HOME);
  const [dragging, setDragging] = useState(false);
  // Smooth camera: `goal` is where the view is heading; each frame closes part of the gap.
  // Interpolating the visible width (not k) keeps a zoom's anchor point fixed on screen, and
  // x moves the short way round the wrapped world.
  function goTo(target: View, instant = false) {
    goal.current = norm({ ...target, k: Math.min(Math.max(target.k, 1), MAX_K) });
    if (instant || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      cancelAnimationFrame(tween.current);
      tween.current = 0;
      return setView(goal.current);
    }
    if (tween.current) return;
    let last = performance.now();
    const step = (t: number) => {
      const a = 1 - Math.exp(-(t - last) / 110); // frame-rate independent easing
      last = t;
      const c = viewRef.current;
      const g = goal.current;
      let dx = g.x - c.x;
      if (dx > W / 2) dx -= W;
      if (dx < -W / 2) dx += W;
      const cw = W / c.k;
      const w = cw + (W / g.k - cw) * a;
      const done = Math.abs(w - W / g.k) < 0.05 && Math.abs(dx) < 0.05 && Math.abs(g.y - c.y) < 0.05;
      const next = done ? g : norm({ k: W / w, x: c.x + dx * a, y: c.y + (g.y - c.y) * a });
      viewRef.current = next;
      setView(next);
      tween.current = done ? 0 : requestAnimationFrame(step);
    };
    tween.current = requestAnimationFrame(step);
  }
  const flyTo = (target: View) => goTo(target);

  /** Zoom by a factor around a screen fraction (rx, ry); builds on the goal so repeated input adds up. */
  function zoomAround(f: number, rx = 0.5, ry = 0.5) {
    const g = goal.current;
    const gx = g.x + rx * (W / g.k);
    const gy = g.y + ry * (H / g.k);
    goTo(zoomAt(g, g.k * f, gx, gy));
  }

  // Selecting a city (leaderboard or list) centres the map on it.
  useEffect(() => {
    const c = cities.find((x) => x.region_id === activeId);
    if (!c) return;
    const k = Math.max(viewRef.current.k, 2.5);
    flyTo({ k, x: px(c.lon) - W / (2 * k), y: py(c.lat) - H / (2 * k) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  useEffect(() => () => cancelAnimationFrame(tween.current), []);

  // Trackpad pinch (sent as ctrl+wheel) and ctrl/cmd+wheel zoom; a plain scroll keeps scrolling the page.
  const zoomRef = useRef(zoomAround);
  zoomRef.current = zoomAround;
  useEffect(() => {
    const el = svgRef.current!;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const lines = e.deltaMode === 1 ? 16 : 1;
      zoomRef.current(Math.exp(-e.deltaY * lines * 0.006), (e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const onPointerDown = (e: PointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    cancelAnimationFrame(tween.current);
    tween.current = 0;
    drag.current = { id: e.pointerId, px: e.clientX, py: e.clientY, v: viewRef.current, moved: false };
  };
  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    const r = svgRef.current!.getBoundingClientRect();
    const dx = e.clientX - d.px;
    const dy = e.clientY - d.py;
    if (!d.moved && Math.hypot(dx, dy) < 4) return; // still a click, not a drag
    if (!d.moved) {
      d.moved = true;
      setDragging(true);
      svgRef.current!.setPointerCapture(e.pointerId); // capture only once it's a drag, so pin clicks still work
    }
    goTo({ k: d.v.k, x: d.v.x - (dx / r.width) * (W / d.v.k), y: d.v.y - (dy / r.height) * (H / d.v.k) }, true);
  };
  const endDrag = () => {
    justDragged.current = !!drag.current?.moved;
    drag.current = null;
    setDragging(false);
  };

  const zoomBy = (f: number) => zoomAround(f);
  const onKeyDown = (e: KeyboardEvent<SVGSVGElement>) => {
    const pan = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    const g = goal.current;
    if (pan) goTo({ k: g.k, x: g.x + (pan[0]! * W) / (8 * g.k), y: g.y + (pan[1]! * H) / (8 * g.k) });
    else if (e.key === "+" || e.key === "=") zoomBy(1.6);
    else if (e.key === "-") zoomBy(1 / 1.6);
    else if (e.key === "0") flyTo(HOME);
    else return;
    e.preventDefault();
  };

  const tiles = useMemo(() => crowds(cities), [cities]);
  const isTop = (rank: number, c: City) => rank < 3 && c.score > 1;
  // Pins keep a constant on-screen size, so the de-overlap re-runs on every zoom frame (18 pins: cheap);
  // zooming in lets nudged pins glide back onto their true locations instead of snapping in steps.
  const s = Math.round(1000 / view.k) / 1000;
  const pins = useMemo(
    () => layoutPins(cities, (i) => (isTop(i, cities[i]!) ? PIN_R_TOP : PIN_R) * s, 2 * s),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cities, s],
  );

  // Land and crowds never change with the camera: built once.
  const base = useMemo(
    () => (
      <>
        <path className="land" d={LAND_PATH} />
        <line className="equator" x1={0} x2={W} y1={py(0)} y2={py(0)} vectorEffect="non-scaling-stroke" />
        {cities.map((c, rank) => (
          <g key={`crowd-${c.region_id}`} className={`crowd ${isTop(rank, c) ? "hot" : c.score > 1 ? "" : "cold"}`}>
            {tiles.get(c.region_id)!.map(([col, row], i) => (
              <rect
                key={i}
                x={r2(col * CELL)}
                y={r2(row * CELL)}
                width={TILE}
                height={TILE}
                style={{ animationDelay: `${rank * 140 + 200 + i * 35}ms` }}
              />
            ))}
          </g>
        ))}
      </>
    ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cities, tiles],
  );

  // Pins follow the zoom continuously; only this small layer re-renders while the camera moves.
  const pinLayer = useMemo(
    () => (
      <>
        {/* Pins drawn last so no crowd covers a rank number; better ranks on top. */}
        {[...cities.entries()].reverse().map(([rank, c]) => {
          const p = pins[rank]!;
          const top = isTop(rank, c);
          return (
            <g
              key={c.region_id}
              className={`pin ${top ? "top" : ""} ${c.score <= 1 ? "dim" : ""} ${activeId === c.region_id ? "active" : ""}`}
              onClick={() => !justDragged.current && onSelect?.(c.region_id)}
            >
              <title>{`${rank + 1}. ${c.name}, ${c.country}: spawn score ×${fmtLift(c.score)}, ${c.confidence} confidence`}</title>
              {(p.x !== px(c.lon) || p.y !== py(c.lat)) && (
                <>
                  <line className="leader" x1={px(c.lon)} y1={py(c.lat)} x2={p.x} y2={p.y} vectorEffect="non-scaling-stroke" />
                  <circle className="anchor" cx={px(c.lon)} cy={py(c.lat)} r={1.8 * s} />
                </>
              )}
              <circle className="ring" cx={p.x} cy={p.y} r={PIN_R * s} vectorEffect="non-scaling-stroke" style={{ animationDelay: `${rank * 140}ms` }} />
              <circle
                className="core"
                cx={p.x}
                cy={p.y}
                r={(top ? PIN_R_TOP : PIN_R) * s}
                vectorEffect="non-scaling-stroke"
                style={{ animationDelay: `${rank * 140}ms` }}
              />
              <text x={p.x} y={p.y} dy="0.35em" textAnchor="middle" style={{ fontSize: (top ? 10 : 9) * s, animationDelay: `${rank * 140 + 150}ms` }}>
                {rank + 1}
              </text>
            </g>
          );
        })}
      </>
    ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cities, pins, s, activeId],
  );
  const world = (
    <>
      {base}
      {pinLayer}
    </>
  );

  return (
    <figure className="map" aria-label="Map of cities ranked by spawn score">
      <svg
        ref={svgRef}
        viewBox={`${r2(view.x)} ${r2(view.y)} ${r2(W / view.k)} ${r2(H / view.k)}`}
        role="img"
        tabIndex={0}
        aria-label="Spawn map. Drag or use arrow keys to pan, plus and minus to zoom, 0 to reset."
        className={dragging ? "dragging" : ""}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={(e) => {
          const r = svgRef.current!.getBoundingClientRect();
          zoomAround(2, (e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
        }}
        onKeyDown={onKeyDown}
      >
        <title>Spawn map: the bigger a city&apos;s crowd, the more your players over-index there</title>
        {/* Two copies side by side: with the viewBox x wrapped into [0, W), the seam is always covered. */}
        <g>{world}</g>
        <g transform={`translate(${W} 0)`} aria-hidden>
          {world}
        </g>
      </svg>
      <div className="map-zoom no-print">
        <button type="button" onClick={() => zoomBy(1.6)} aria-label="Zoom in" disabled={view.k >= MAX_K}>
          +
        </button>
        <button type="button" onClick={() => zoomBy(1 / 1.6)} aria-label="Zoom out" disabled={view.k <= 1}>
          −
        </button>
        <button type="button" onClick={() => flyTo(HOME)} aria-label="Reset map view" className="label">
          Reset
        </button>
      </div>
      <figcaption className="map-hud">
        <div className="map-board">
          <span className="label muted">Top spawn points</span>
          <ol>
            {cities.slice(0, 3).map((c, i) => (
              <li key={c.region_id} style={{ ["--i" as string]: i }}>
                <button type="button" onClick={() => (onSelect ? onSelect(c.region_id) : flyTo({ k: 2.5, x: px(c.lon) - W / 5, y: py(c.lat) - H / 5 }))}>
                  <span className={`rank-badge ${isTop(i, c) ? "hot" : ""}`}>{i + 1}</span>
                  <span className="board-name">{c.name}</span>
                  <span className="num">×{fmtLift(c.score)}</span>
                </button>
              </li>
            ))}
          </ol>
        </div>
        <span className="label muted map-key">
          <i className="key-tile hot" /> top 3 crowd <i className="key-tile" /> over-indexes <i className="key-tile cold" />{" "}
          below average · 1 tile = +0.02 spawn score · drag to explore
        </span>
      </figcaption>
    </figure>
  );
}
