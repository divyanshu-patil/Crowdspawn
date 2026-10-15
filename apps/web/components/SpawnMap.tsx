"use client";

import type { City } from "@repo/contracts";
import { lift as fmtLift } from "../lib/format";

const W = 1000;
const H = 440;
const LAT_TOP = 68;
const LAT_BOTTOM = -48;

// Equirectangular projection cropped to where the candidate cities live.
// Rounded so server and client render identical attribute strings (no hydration mismatch).
const r1 = (n: number) => Math.round(n * 10) / 10;
const x = (lon: number) => r1(((lon + 180) / 360) * W);
const y = (lat: number) => r1(((LAT_TOP - lat) / (LAT_TOP - LAT_BOTTOM)) * H);
const LABEL_DY = [-16, 30, 46]; // stagger top-3 labels so nearby cities (Tokyo/Seoul) don't collide

/** Deterministic pseudo-random so a city's crowd looks the same on every render. */
function rand(seed: string, i: number) {
  let h = 2166136261;
  for (const ch of seed + i) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return ((h >>> 0) % 1000) / 1000;
}

/** Crowd size: one pixel per 0.02 of lift above 1, capped. Under-indexing cities get one. */
export const crowdSize = (lift: number) => Math.max(1, Math.min(24, Math.round((lift - 1) / 0.02)));

export function SpawnMap({
  cities,
  activeId,
  onSelect,
}: {
  cities: City[];
  activeId?: string | null;
  onSelect?: (id: string) => void;
}) {
  const ranked = cities.map((c, rank) => ({ c, rank }));
  return (
    <figure className="map" aria-label="Map of cities ranked by fan affinity lift">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-hidden={false}>
        <title>Spawn map: larger crowds mean fans of your comps over-index more in that city</title>
        {Array.from({ length: 13 }, (_, i) => (
          <line key={`v${i}`} className="gridline" x1={(i * W) / 12} x2={(i * W) / 12} y1={0} y2={H} />
        ))}
        {Array.from({ length: 6 }, (_, i) => (
          <line key={`h${i}`} className="gridline" y1={(i * H) / 5} y2={(i * H) / 5} x1={0} x2={W} />
        ))}
        <line className="equator" x1={0} x2={W} y1={y(0)} y2={y(0)} />
        {ranked.map(({ c, rank }) => {
          const cx = x(c.lon);
          const cy = y(c.lat);
          const n = crowdSize(c.lift);
          const top = rank < 3 && c.lift > 1;
          const delay = rank * 140;
          return (
            <g key={c.region_id}>
              <g className={`crowd ${top ? "hot" : ""}`}>
                {Array.from({ length: n }, (_, i) => {
                  const a = rand(c.region_id, i) * Math.PI * 2;
                  const r = 12 + rand(c.region_id, i + 99) * (10 + n * 1.4);
                  return (
                    <rect
                      key={i}
                      x={r1(cx + Math.cos(a) * r - 2.5)}
                      y={r1(cy + Math.sin(a) * r - 2.5)}
                      width={5}
                      height={5}
                      style={{ animationDelay: `${delay + 200 + i * 35}ms` }}
                    />
                  );
                })}
              </g>
              <g
                className={`pin ${top ? "top" : ""} ${c.lift <= 1 ? "dim" : ""} ${activeId === c.region_id ? "active" : ""}`}
                onClick={() => onSelect?.(c.region_id)}
              >
                <circle className="ring" cx={cx} cy={cy} r={9} style={{ animationDelay: `${delay}ms` }} />
                <circle className="core" cx={cx} cy={cy} r={top ? 8 : 6} style={{ animationDelay: `${delay}ms` }} />
                <text
                  x={cx > W * 0.75 ? cx - 14 : cx + 14}
                  y={cy + (top ? LABEL_DY[rank]! : -12)}
                  textAnchor={cx > W * 0.75 ? "end" : "start"}
                  style={{ animationDelay: `${delay + 150}ms` }}
                >
                  {top ? `${rank + 1} ${c.name} ×${fmtLift(c.lift)}` : rank + 1}
                </text>
              </g>
            </g>
          );
        })}
      </svg>
      <figcaption className="map-legend">
        <span className="label">Crowd size = lift over mainstream gamers</span>
        <span className="label">Orange = top 3 spawn points</span>
      </figcaption>
    </figure>
  );
}
