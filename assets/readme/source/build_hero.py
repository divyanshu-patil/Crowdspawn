"""Build assets/readme/hero.svg from the app's own pixel country map and the sample plan.

Countries come from apps/web/lib/countries.ts (Natural Earth, one tile = 2 degrees) and the three spawn
points from apps/web/public/sample-plan.json.
Run from the repo root: python3 assets/readme/source/build_hero.py
"""

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "apps/web"
src = (WEB / "lib/countries.ts").read_text()
line = next(ln for ln in src.splitlines() if ln.startswith("export const COUNTRIES"))
COUNTRIES = json.loads(line[line.index("= [") + 2 :].rstrip(";"))
PLAN = json.loads((WEB / "public/sample-plan.json").read_text())

INK, CANVAS, PAPER, MIST, HAIR, SOFT = "#141414", "#f5f5f5", "#ffffff", "#e9e9e9", "#d9d9d9", "#5c5c5c"
MARKER, EMBER, SIGNAL = "#fecc33", "#ff8400", "#30a81d"
SANS = "'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

# Map crop in tile units (cols 96-144 = 12E-108E, rows 8-34 = 58N-6N: Warsaw, Istanbul and Delhi for the
# Long Haul sample) and its place in the hero. A new sample may need a new crop.
C0, R0, CW, RH = 96, 8, 48, 26
S = 9.4
MX, MY = 690, 64


def in_crop(d: str) -> str:
    """Keep only the row runs of a country path that touch the crop (the clip trims the rest)."""
    keep = []
    for m in re.finditer(r"M(\d+) (\d+)h(\d+)v1h-\d+z", d):
        x, y, w = map(int, m.groups())
        if R0 <= y < R0 + RH and x + w > C0 and x < C0 + CW:
            keep.append(m.group(0))
    return "".join(keep)


def xy(lat: float, lon: float) -> tuple[float, float]:
    return (lon + 180) / 2, (74 - lat) / 2


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;")


countries = []
for c in COUNTRIES:
    d = in_crop(c["d"])
    if not d:
        continue
    countries.append(f'<path d="{d}" fill="{MIST}"/>')

# Spawn crowds: a lifted block of tiles around each top city, sized by spawn score.
top = PLAN["cities"][:3]
crowds, badges = [], []
for i, city in enumerate(top, 1):
    cx, cy = xy(city["lat"], city["lon"])
    r = 1.3 + city["score"] * 0.75
    tiles = [
        (x, y)
        for x in range(math.floor(cx - r), math.ceil(cx + r))
        for y in range(math.floor(cy - r), math.ceil(cy + r))
        if (x + 0.5 - cx) ** 2 + ((y + 0.5 - cy) * 1.15) ** 2 <= r * r
    ]
    side = "".join(f"M{x + 0.22} {y + 0.22}h1v1h-1z" for x, y in tiles)
    top_ = "".join(f"M{x} {y}h1v1h-1z" for x, y in tiles)
    crowds.append(f'<path d="{side}" fill="{INK}"/><path d="{top_}" fill="{EMBER}"/>')
    bx, by = MX + (cx - C0) * S, MY + (cy - R0) * S
    badges.append(
        f'<g transform="translate({bx:.1f} {by:.1f})"><circle r="15" fill="{PAPER}" stroke="{INK}" stroke-width="2.5"/>'
        f'<text y="6.5" text-anchor="middle" font-family="{MONO}" font-size="18" font-weight="700" fill="{INK}">{i}</text></g>'
    )

rows = "".join(
    f'<g transform="translate(0 {66 + j * 34})">'
    f'<circle cx="12" cy="-6" r="11" fill="{EMBER}" stroke="{INK}" stroke-width="2"/>'
    f'<text x="12" y="-0.5" text-anchor="middle" font-family="{MONO}" font-size="13" font-weight="700" fill="{INK}">{j + 1}</text>'
    f'<text x="34" y="0" font-family="{SANS}" font-size="20" fill="{INK}">{esc(c["name"])}</text>'
    f'<text x="196" y="0" text-anchor="end" font-family="{MONO}" font-size="20" fill="{INK}">×{c["score"]:.2f}</text></g>'
    for j, c in enumerate(top)
)

W, H = 1200, 440
mw, mh = CW * S, RH * S
svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">
  <title id="title">Crowdspawn: find where your players already are, and who else they love, before launch day</title>
  <desc id="desc">Pixel map from Central Europe to India with the sample plan's top spawn points: {", ".join(f"{c['name']} {c['score']:.2f}" for c in top)}.</desc>
  <defs>
    <pattern id="sketch" width="36" height="36" patternUnits="userSpaceOnUse" x="-1" y="-1">
      <path d="M36 0H0V36" fill="none" stroke="{HAIR}" stroke-width="1"/>
    </pattern>
    <pattern id="pix" width="1" height="1" patternUnits="userSpaceOnUse">
      <path d="M1 0V1H0" fill="none" stroke="{PAPER}" stroke-width="0.12"/>
    </pattern>
    <clipPath id="crop"><rect x="{C0}" y="{R0}" width="{CW}" height="{RH}"/></clipPath>
  </defs>

  <rect width="{W}" height="{H}" rx="24" fill="{CANVAS}"/>
  <rect width="{W}" height="{H}" rx="24" fill="url(#sketch)"/>

  <g id="title-block" transform="translate(56 0)">
    <circle cx="8" cy="86" r="6" fill="{SIGNAL}"/>
    <text x="24" y="92" font-family="{MONO}" font-size="18" letter-spacing="1.5" fill="{SOFT}">LAUNCH PLANNER FOR INDIE GAMES</text>
    <text x="-4" y="196" font-family="{SANS}" font-size="94" font-weight="700" letter-spacing="-3.5" fill="{INK}">Crowdspawn</text>
    <text x="0" y="256" font-family="{SANS}" font-size="29" fill="{INK}">Find where your players already are,</text>
    <text x="0" y="294" font-family="{SANS}" font-size="29" fill="{INK}">and who else they love, before launch day.</text>
    <g font-family="{MONO}" font-size="16" letter-spacing="1" transform="translate(0 340)">
      <rect x="4" y="4" width="166" height="40" rx="8" fill="{INK}"/>
      <rect width="166" height="40" rx="8" fill="{INK}"/>
      <text x="83" y="26" text-anchor="middle" fill="{PAPER}">LAUNCH AGENT</text>
      <rect x="182" y="4" width="160" height="40" rx="8" fill="{INK}"/>
      <rect x="178" width="160" height="40" rx="8" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>
      <text x="258" y="26" text-anchor="middle" fill="{INK}">LAUNCH PLAN</text>
      <rect x="354" y="4" width="166" height="40" rx="8" fill="{INK}"/>
      <rect x="350" width="166" height="40" rx="8" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>
      <text x="433" y="26" text-anchor="middle" fill="{INK}">REGION SCOUT</text>
    </g>
    <text x="0" y="410" font-family="{MONO}" font-size="15" letter-spacing="1" fill="{SOFT}">DATA: QLOO TASTE AI · AFFINITY INDEX, NOT A SALES FORECAST</text>
  </g>

  <g id="project-proof">
    <rect x="{MX - 14 + 6}" y="{MY - 14 + 6}" width="{mw + 28}" height="{mh + 28}" rx="16" fill="{INK}"/>
    <rect x="{MX - 14}" y="{MY - 14}" width="{mw + 28}" height="{mh + 28}" rx="16" fill="{PAPER}" stroke="{INK}" stroke-width="2.5"/>
    <g transform="translate({MX - C0 * S} {MY - R0 * S}) scale({S})" clip-path="url(#crop)">
      {"".join(countries)}
      {"".join(crowds)}
      <rect x="{C0}" y="{R0}" width="{CW}" height="{RH}" fill="url(#pix)"/>
    </g>
    {"".join(badges)}
    <g id="spawn-card" transform="translate({MX - 14} {MY + mh - 94})">
      <rect x="5" y="5" width="232" height="160" rx="12" fill="{INK}"/>
      <rect width="232" height="160" rx="12" fill="{PAPER}" stroke="{INK}" stroke-width="2.5"/>
      <g transform="translate(16 0)">
        <text y="30" font-family="{MONO}" font-size="14" letter-spacing="1.5" fill="{SOFT}">TOP SPAWN POINTS</text>
        {rows}
      </g>
    </g>
    <text x="{MX + mw + 14}" y="{MY + mh + 48}" text-anchor="end" font-family="{MONO}" font-size="15" letter-spacing="1" fill="{SOFT}">SAMPLE PLAN</text>
    <text x="{MX + mw + 14}" y="{MY + mh + 72}" text-anchor="end" font-family="{MONO}" font-size="15" letter-spacing="1" fill="{SOFT}">{esc(PLAN["input"]["game"]["title"].upper())}</text>
  </g>
</svg>
"""
out = ROOT / "assets/readme/hero.svg"
out.write_text(svg)
print(out, len(svg), "bytes")
