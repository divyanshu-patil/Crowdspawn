"""Accuracy backtest: does the shipped spawn score carry signal beyond popularity?

For each shipped game we run S1-S3 with comps that are NOT the game, aggregate city spawn scores
(taste lift x PC platform fit; Steam is PC) to Steam languages, and compare with a public proxy: the
game's Steam review share per language divided by the mean share of mainstream Steam hits (so the
proxy is also an over-index). We report top-3 hit rate and Spearman for (a) the spawn score and
(b) the popularity ranking (all-gamers panels alone).

Live: ~130 Qloo calls on a cold cache, plus Steam's public review endpoint. Writes docs/backtest-results.md.
Run: uv run python scripts/backtest.py
"""

import asyncio
import json
import statistics
from datetime import date
from pathlib import Path

import httpx

from crowdspawn_api.pipeline import cities, expand, resolve
from crowdspawn_api.qloo.client import QlooClient
from crowdspawn_api.schemas import Comp
from crowdspawn_api.settings import get_settings
from crowdspawn_api.storage import Store

ROOT = Path(__file__).resolve().parents[3]
LANG = {  # city id -> Steam review language
    "nyc": "english",
    "lax": "english",
    "sfo": "english",
    "sea": "english",
    "aus": "english",
    "chi": "english",
    "yto": "english",
    "lon": "english",
    "syd": "english",
    "sin": "english",
    "ber": "german",
    "par": "french",
    "sto": "swedish",
    "waw": "polish",
    "tyo": "japanese",
    "sel": "koreana",
    "sao": "brazilian",
    "mex": "latam",
}
LANGS = sorted(set(LANG.values()))
GAMES = [  # (title, steam appid, comps that are not the game)
    ("Hades", 1145360, ["Dead Cells", "Bastion", "Transistor"]),
    ("Stardew Valley", 413150, ["Story of Seasons", "Animal Crossing: New Horizons", "Terraria"]),
    ("Hollow Knight", 367520, ["Ori and the Blind Forest", "Dead Cells", "Celeste"]),
    ("Celeste", 504230, ["Super Meat Boy", "Hollow Knight", "Shovel Knight"]),
    ("Vampire Survivors", 1794680, ["Brotato", "Risk of Rain 2", "Enter the Gungeon"]),
    (
        "Disco Elysium",
        632470,
        ["Planescape: Torment", "Pillars of Eternity", "Divinity: Original Sin 2"],
    ),
]
MAINSTREAM_STEAM = [271590, 1245620, 1091500]  # GTA V, Elden Ring, Cyberpunk 2077


def spearman(a: list[float], b: list[float]) -> float:
    def ranks(x: list[float]) -> list[float]:
        order = sorted(range(len(x)), key=lambda i: x[i])
        r = [0.0] * len(x)
        for pos, i in enumerate(order):
            r[i] = float(pos)
        return r

    return statistics.correlation(ranks(a), ranks(b))


def top(x: dict[str, float], n: int) -> list[str]:
    return sorted(x, key=lambda k: -x[k])[:n]


async def steam_shares(http: httpx.AsyncClient, appid: int) -> dict[str, float]:
    counts = {}
    for lang in LANGS:
        r = await http.get(
            f"https://store.steampowered.com/appreviews/{appid}",
            params={"json": 1, "language": lang, "purchase_type": "all", "num_per_page": 0},
        )
        counts[lang] = r.json()["query_summary"]["total_reviews"]
        await asyncio.sleep(0.4)
    total = sum(counts.values()) or 1
    return {k: v / total for k, v in counts.items()}


async def main() -> None:
    s = get_settings()
    store = await Store.open(s.db_file)
    qloo = QlooClient(s, store)
    rows, lines = [], []
    try:
        async with httpx.AsyncClient(timeout=30) as steam:
            mainstream = [await steam_shares(steam, a) for a in MAINSTREAM_STEAM]
            norm = {lang: statistics.fmean(m[lang] for m in mainstream) for lang in LANGS}
            for title, appid, comp_names in GAMES:
                run = qloo.run(max_calls=80)
                found, dropped = await resolve.resolve_names(run, comp_names)
                comps = [
                    Comp(entity_id=f.resolved.entity_id, name=f.resolved.name, result_id="-")
                    for f in found
                    if f.resolved
                ]
                expanded = await expand.expand(run, comps)
                ranked, _ = await cities.score_cities(
                    run, list(LANG), expand.signal_ids(comps, expanded), ["pc"]
                )
                by_lang_lift: dict[str, list[float]] = {}
                by_lang_base: dict[str, list[float]] = {}
                by_lang_target: dict[str, list[float]] = {}
                for c in ranked:
                    by_lang_target.setdefault(LANG[c.region_id], []).append(c.target_score)
                    by_lang_lift.setdefault(LANG[c.region_id], []).append(c.score)
                    by_lang_base.setdefault(LANG[c.region_id], []).append(c.baseline_score)
                langs = [lang for lang in LANGS if lang in by_lang_lift]
                q = {lang: statistics.fmean(by_lang_lift[lang]) for lang in langs}
                b = {lang: statistics.fmean(by_lang_base[lang]) for lang in langs}
                t = {lang: statistics.fmean(by_lang_target[lang]) for lang in langs}
                shares = await steam_shares(steam, appid)
                proxy = {lang: shares[lang] / max(norm[lang], 1e-9) for lang in langs}
                truth3 = top(proxy, 3)
                row = {
                    "game": title,
                    "comps": [c.name for c in comps],
                    "dropped": dropped,
                    "proxy_top3": truth3,
                    "qloo_top3": top(q, 3),
                    "qloo_top3_hits": len(set(truth3) & set(top(q, 3))),
                    "qloo_top5_hits": len(set(truth3) & set(top(q, 5))),
                    "qloo_spearman": round(
                        spearman([q[k] for k in langs], [proxy[k] for k in langs]), 2
                    ),
                    "base_top3": top(b, 3),
                    "base_top3_hits": len(set(truth3) & set(top(b, 3))),
                    "base_top5_hits": len(set(truth3) & set(top(b, 5))),
                    "base_spearman": round(
                        spearman([b[k] for k in langs], [proxy[k] for k in langs]), 2
                    ),
                    "target_top3_hits": len(set(truth3) & set(top(t, 3))),
                    "target_spearman": round(
                        spearman([t[k] for k in langs], [proxy[k] for k in langs]), 2
                    ),
                    "calls": run.calls,
                }
                rows.append(row)
                print(json.dumps(row))
    finally:
        print("live Qloo calls", qloo.live_calls)
        await qloo.aclose()
        await store.close()

    def avg(k: str) -> float:
        return round(statistics.fmean(r[k] for r in rows), 2)

    wins = sum(r["qloo_spearman"] > r["base_spearman"] for r in rows)
    lines += [
        "# Backtest results",
        "",
        f"Run on {date.today().isoformat()} with `apps/api/scripts/backtest.py`. City-level truth is not public, so this tests **language-level** signal only.",
        "",
        "**Proxy:** each game's Steam review share per language, divided by the mean share for mainstream Steam hits (GTA V, Elden Ring, Cyberpunk 2077), so it measures over-indexing like Qloo's lift. "
        "**Qloo ranking:** mean city spawn score per language (taste lift × PC platform fit, the shipped scorer). **Baseline-only ranking:** mean all-gamers heatmap score per language (PC, mobile and console panels: what you'd get from popularity alone). "
        f"Languages compared: {', '.join(LANGS)} ({len(LANGS)}); English is the mean of 10 cities.",
        "",
        "| Game | Comps used | Proxy top 3 | Qloo top 3 | Qloo hits in top 3 / top 5 | Qloo ρ | Baseline hits top 3 / top 5 | Baseline ρ |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['game']} | {', '.join(r['comps'])} | {', '.join(r['proxy_top3'])} | {', '.join(r['qloo_top3'])} "
            f"| {r['qloo_top3_hits']}/3 · {r['qloo_top5_hits']}/3 | {r['qloo_spearman']} "
            f"| {r['base_top3_hits']}/3 · {r['base_top5_hits']}/3 | {r['base_spearman']} |"
        )
    lines += [
        "",
        f"**Averages:** Qloo top-3 hits {avg('qloo_top3_hits')}/3, top-5 {avg('qloo_top5_hits')}/3, Spearman {avg('qloo_spearman')}. "
        f"Baseline-only top-3 hits {avg('base_top3_hits')}/3, top-5 {avg('base_top5_hits')}/3, Spearman {avg('base_spearman')}. "
        f"Qloo's Spearman beat the baseline in {wins} of {len(rows)} games. "
        f"For reference, the raw comp-set heatmap score (no baseline division) averaged top-3 hits "
        f"{avg('target_top3_hits')}/3 and Spearman {avg('target_spearman')}.",
        "",
        "## Caveats",
        "",
        "- Steam review language is a rough proxy for where players are: it misses console players, people who review in English from non-English countries, and markets where Steam is small.",
        f"- {len(LANGS)} languages is a small ranking; one swap moves Spearman a lot.",
        "- Qloo's lift compares against all gamers (PC, mobile and console panels), not Steam users specifically.",
        "- This says nothing about city-level accuracy. Treat the city ranking as a taste-informed starting hypothesis.",
    ]
    out = ROOT / "docs" / "backtest-results.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
