// Generates lib/countries.ts: pixel-tile countries with borders for the region scout map, from Natural Earth
// (world-atlas). One-off; the output is committed so the app has no map dependency at runtime.
// Run: npm i world-atlas@2.0.2 topojson-client@3.1.0 d3-geo@3.1.1 in some scratch dir, then
//      node scripts/gen-countries.mjs <that-dir>/node_modules
import { readFileSync, writeFileSync } from "node:fs";
import process from "node:process";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const mods = process.argv[2];
const { feature } = await import(pathToFileURL(join(mods, "topojson-client/src/index.js")));
const { geoContains, geoBounds } = await import(pathToFileURL(join(mods, "d3-geo/src/index.js")));
const topo = JSON.parse(readFileSync(join(mods, "world-atlas/countries-50m.json"), "utf8"));
const countries = feature(topo, topo.objects.countries).features;

const STEP = 2;
const LAT_TOP = 74;
const LAT_BOTTOM = -56;
const COLS = 360 / STEP;
const ROWS = (LAT_TOP - LAT_BOTTOM) / STEP;
const SUB = [0.2, 0.5, 0.8];

// ISO numeric -> alpha-2 for countries the API has readings for (apps/api/.../cities.json, scout_points.json).
const A2 = {
  840: "US", 124: "CA", 826: "GB", 276: "DE", 250: "FR", 752: "SE", 616: "PL", 203: "CZ", 724: "ES", 792: "TR",
  356: "IN", 784: "AE", 392: "JP", 410: "KR", 36: "AU", 702: "SG", 360: "ID", 608: "PH", 76: "BR", 484: "MX",
  32: "AR", 566: "NG", 818: "EG", 710: "ZA", 404: "KE", 504: "MA", 682: "SA", 376: "IL", 586: "PK", 50: "BD",
  764: "TH", 704: "VN", 458: "MY", 158: "TW", 344: "HK", 156: "CN", 604: "PE", 170: "CO", 152: "CL", 380: "IT",
  528: "NL", 620: "PT", 578: "NO", 246: "FI", 40: "AT", 300: "GR", 642: "RO", 804: "UA", 554: "NZ", 643: "RU",
  208: "DK", 372: "IE", 56: "BE", 756: "CH", 348: "HU",
};
const BY_NAME = { Norway: "NO", France: "FR" }; // Natural Earth leaves these ids blank in some builds

// Small places that vanish at 2 degrees but have readings: force their tile.
const FORCE = { SG: [1.35, 103.82], HK: [22.32, 114.17], IL: [32.08, 34.78], AE: [25.2, 55.27], TW: [25.03, 121.57] };

const boxes = countries.map((f) => geoBounds(f));
const grid = Array.from({ length: ROWS }, () => new Array(COLS).fill(-1));
for (let r = 0; r < ROWS; r++) {
  for (let c = 0; c < COLS; c++) {
    const votes = new Map();
    for (const sy of SUB)
      for (const sx of SUB) {
        const lon = -180 + (c + sx) * STEP;
        const lat = LAT_TOP - (r + sy) * STEP;
        for (let i = 0; i < countries.length; i++) {
          const [[w, s], [e, n]] = boxes[i];
          const inLon = w <= e ? lon >= w && lon <= e : lon >= w || lon <= e;
          if (!inLon || lat < s || lat > n) continue;
          if (geoContains(countries[i], [lon, lat])) {
            votes.set(i, (votes.get(i) ?? 0) + 1);
            break;
          }
        }
      }
    let best = -1;
    let most = 2; // at least 3 of 9 samples on land
    for (const [i, v] of votes) if (v > most) [best, most] = [i, v];
    grid[r][c] = best;
  }
}

const a2Of = (i) => A2[Number(countries[i].id)] ?? BY_NAME[countries[i].properties.name] ?? null;
for (const [code, [lat, lon]] of Object.entries(FORCE)) {
  const i = countries.findIndex((_, k) => a2Of(k) === code);
  if (i < 0) continue;
  const r = Math.floor((LAT_TOP - lat) / STEP);
  const c = Math.floor((lon + 180) / STEP);
  grid[r][c] = i;
}

/** Row runs of a country's tiles as one compact path. */
function fillPath(i) {
  let d = "";
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      if (grid[r][c] !== i) continue;
      let e = c;
      while (e + 1 < COLS && grid[r][e + 1] === i) e++;
      d += `M${c} ${r}h${e - c + 1}v1h${-(e - c + 1)}z`;
      c = e;
    }
  }
  return d;
}

/** The country's outline: tile edges where the neighbour is another country or sea, merged into runs. */
function borderPath(i) {
  const at = (r, c) => (r < 0 || r >= ROWS ? -1 : grid[r][(c + COLS) % COLS]);
  let d = "";
  for (let r = 0; r <= ROWS; r++) {
    for (const side of [0, 1]) {
      // side 0: top edge of row r; side 1: bottom edge of row r-1 (same line, other owner)
      for (let c = 0; c < COLS; c++) {
        const edge = (k) => (side === 0 ? at(r, k) === i && at(r - 1, k) !== i : at(r - 1, k) === i && at(r, k) !== i);
        if (!edge(c)) continue;
        let e = c;
        while (e + 1 < COLS && edge(e + 1)) e++;
        d += `M${c} ${r}h${e - c + 1}`;
        c = e;
      }
    }
  }
  for (let c = 0; c <= COLS; c++) {
    for (const side of [0, 1]) {
      for (let r = 0; r < ROWS; r++) {
        const edge = (k) => (side === 0 ? at(k, c) === i && at(k, c - 1) !== i : at(k, c - 1) === i && at(k, c) !== i);
        if (!edge(r)) continue;
        let e = r;
        while (e + 1 < ROWS && edge(e + 1)) e++;
        d += `M${c} ${r}v${e - r + 1}`;
        r = e;
      }
    }
  }
  return d;
}

const out = [];
for (let i = 0; i < countries.length; i++) {
  const d = fillPath(i);
  if (!d) continue;
  let n = 0;
  let sr = 0;
  let sc = 0;
  for (let r = 0; r < ROWS; r++)
    for (let c = 0; c < COLS; c++)
      if (grid[r][c] === i) {
        n++;
        sr += r;
        sc += c;
      }
  out.push({
    id: String(countries[i].id ?? countries[i].properties.name),
    name: countries[i].properties.name,
    a2: a2Of(i),
    tiles: n,
    cx: +(sc / n + 0.5).toFixed(1),
    cy: +(sr / n + 0.5).toFixed(1),
    d,
    b: borderPath(i),
  });
}
out.sort((a, b) => b.tiles - a.tiles);

const ts = `// Generated by scripts/gen-countries.mjs from Natural Earth 1:50m countries (world-atlas). Do not edit.
// Tile units: one tile is ${STEP} degrees; x = (lon + 180) / ${STEP}, y = (${LAT_TOP} - lat) / ${STEP}.
export const GRID = { step: ${STEP}, latTop: ${LAT_TOP}, cols: ${COLS}, rows: ${ROWS} } as const;
export type CountryShape = { id: string; name: string; a2: string | null; tiles: number; cx: number; cy: number; d: string; b: string };
export const COUNTRIES: CountryShape[] = ${JSON.stringify(out)};
`;
writeFileSync(new URL("../lib/countries.ts", import.meta.url), ts);
console.log(`${out.length} countries, ${(ts.length / 1024).toFixed(0)} KB, with a2: ${out.filter((c) => c.a2).length}`);
