"use client";

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

/** Crowd size in tiles: one per 0.02 of lift above 1, capped. Under-indexing cities get one. */
export const crowdSize = (lift: number) => Math.max(1, Math.min(24, Math.round((lift - 1) / 0.02)));

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
    const picked = candidates.slice(0, crowdSize(city.lift)).map(({ c, r }) => [c, r] as [number, number]);
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
function layoutPins(cities: City[], radius: (i: number) => number) {
  const pos = cities.map((c) => ({ x: px(c.lon), y: py(c.lat) }));
  for (let iter = 0; iter < 60; iter++) {
    let moved = false;
    for (let i = 0; i < pos.length; i++)
      for (let j = i + 1; j < pos.length; j++) {
        const a = pos[i]!;
        const b = pos[j]!;
        const min = radius(i) + radius(j) + 2;
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

export function SpawnMap({
  cities,
  activeId,
  onSelect,
}: {
  cities: City[];
  activeId?: string | null;
  onSelect?: (id: string) => void;
}) {
  const tiles = crowds(cities);
  const isTop = (rank: number, c: City) => rank < 3 && c.lift > 1;
  const pins = layoutPins(cities, (i) => (isTop(i, cities[i]!) ? PIN_R_TOP : PIN_R));
  return (
    <figure className="map" aria-label="Map of cities ranked by fan affinity lift">
      <svg viewBox={`0 0 ${W} ${H}`} role="img">
        <title>Spawn map: the bigger a city&apos;s crowd, the more fans of your comps over-index there</title>
        <path className="land" d={LAND_PATH} />
        <line className="equator" x1={0} x2={W} y1={py(0)} y2={py(0)} />
        {cities.map((c, rank) => (
          <g key={`crowd-${c.region_id}`} className={`crowd ${isTop(rank, c) ? "hot" : c.lift > 1 ? "" : "cold"}`}>
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
        {/* Pins drawn last so no crowd covers a rank number; better ranks on top. */}
        {[...cities.entries()].reverse().map(([rank, c]) => (
          <g
            key={c.region_id}
            className={`pin ${isTop(rank, c) ? "top" : ""} ${c.lift <= 1 ? "dim" : ""} ${activeId === c.region_id ? "active" : ""}`}
            onClick={() => onSelect?.(c.region_id)}
            style={{ cursor: onSelect ? "pointer" : "default" }}
          >
            <title>{`${rank + 1}. ${c.name}, ${c.country}: lift ×${fmtLift(c.lift)}, ${c.confidence} confidence`}</title>
            {(pins[rank]!.x !== px(c.lon) || pins[rank]!.y !== py(c.lat)) && (
              <>
                <line className="leader" x1={px(c.lon)} y1={py(c.lat)} x2={pins[rank]!.x} y2={pins[rank]!.y} />
                <circle className="anchor" cx={px(c.lon)} cy={py(c.lat)} r={1.8} />
              </>
            )}
            <circle className="ring" cx={pins[rank]!.x} cy={pins[rank]!.y} r={PIN_R} style={{ animationDelay: `${rank * 140}ms` }} />
            <circle
              className="core"
              cx={pins[rank]!.x}
              cy={pins[rank]!.y}
              r={isTop(rank, c) ? PIN_R_TOP : PIN_R}
              style={{ animationDelay: `${rank * 140}ms` }}
            />
            <text x={pins[rank]!.x} y={pins[rank]!.y} dy="0.35em" textAnchor="middle" style={{ animationDelay: `${rank * 140 + 150}ms` }}>
              {rank + 1}
            </text>
          </g>
        ))}
      </svg>
      <figcaption className="map-hud">
        <div className="map-board">
          <span className="label muted">Top spawn points</span>
          <ol>
            {cities.slice(0, 3).map((c, i) => (
              <li key={c.region_id} style={{ ["--i" as string]: i }}>
                <button type="button" onClick={() => onSelect?.(c.region_id)} disabled={!onSelect}>
                  <span className={`rank-badge ${isTop(i, c) ? "hot" : ""}`}>{i + 1}</span>
                  <span className="board-name">{c.name}</span>
                  <span className="num">×{fmtLift(c.lift)}</span>
                </button>
              </li>
            ))}
          </ol>
        </div>
        <span className="label muted map-key">
          <i className="key-tile hot" /> top 3 crowd <i className="key-tile" /> over-indexes <i className="key-tile cold" />{" "}
          below baseline · 1 tile = +0.02 lift
        </span>
      </figcaption>
    </figure>
  );
}
