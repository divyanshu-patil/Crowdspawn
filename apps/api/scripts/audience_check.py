"""Audience check: does Qloo's gender skew for a genre match an independent survey?

Truth: the female share of each genre's players from Quantic Foundry's 2017 survey of about 270,000 gamers,
as reported by Game Informer (2017-01-21). Qloo: the "female" index of `urn:demographics` for a panel of
well-known games in that genre. An LLM's guess of each share is reported beside it. Design fixed before any
call (docs/10-risks-decisions.md, local).

  uv run python scripts/audience_check.py          # live: ~25 Qloo calls and 1 LLM call; writes audience_check.json
  uv run python scripts/audience_check.py report   # offline: writes docs/audience-check.md
"""

import asyncio
import json
import sys
from datetime import date

from pydantic import BaseModel
from scenarios import HERE, ROOT, spearman

from crowdspawn_api.llm.registry import build_provider, model_name
from crowdspawn_api.llm.structured import CallBudget, complete_json
from crowdspawn_api.pipeline import demographics, resolve
from crowdspawn_api.qloo.client import QlooClient
from crowdspawn_api.settings import GENRE_PANELS, get_settings
from crowdspawn_api.storage import Store

SOURCE = "https://gameinformer.com/b/news/archive/2017/01/21/study-breaks-down-game-genre-playerbases-by-gender.aspx"
# genre -> (female share %, the app's genre panel or the games chosen for it)
GENRES: dict[str, tuple[float, str | tuple[str, ...]]] = {
    "Match 3": (69, ("Candy Crush Saga", "Bejeweled 3", "Farm Heroes Saga")),
    "Family/Farm Sim": (69, "Cozy and life sim"),
    "Casual Puzzle": (42, ("Cut the Rope", "Monument Valley", "Two Dots")),
    "Atmospheric Exploration": (41, ("Journey", "Firewatch", "Gone Home")),
    "High Fantasy MMO": (36, "MMORPG"),
    "Sci-Fi MMO": (16, ("EVE Online", "Star Wars: The Old Republic", "Star Trek Online")),
    "Fighting": (13.4, "Fighting"),
    "Racing": (6, "Racing"),
    "Tactical Shooter": (
        4,
        ("Tom Clancy's Rainbow Six Siege", "Counter-Strike: Global Offensive", "Arma 3"),
    ),
    "Sports": (2, "Sports"),
}
OUT = HERE / "audience_check.json"


class Shares(BaseModel):
    female_percent: dict[str, float]


async def collect() -> None:
    s = get_settings()
    store = await Store.open(s.db_target)
    qloo = QlooClient(s, store)
    out: dict[str, object] = {"collected": date.today().isoformat(), "source": SOURCE, "genres": {}}
    try:
        run = qloo.run(max_calls=40)
        for genre, (_, panel) in GENRES.items():
            if isinstance(panel, str):
                games = [(n, i) for n, i in GENRE_PANELS[panel]]
                dropped: list[str] = []
            else:
                found, dropped = await resolve.resolve_names(run, list(panel))
                games = [(f.resolved.name, f.resolved.entity_id) for f in found if f.resolved]
            aud = await demographics.audience(run, [i for _, i in games])
            idx = {g.label: g.index for g in aud.gender}
            out["genres"][genre] = {  # type: ignore[index]
                "games": [n for n, _ in games],
                "dropped": dropped,
                "female": idx["female"],
                "male": idx["male"],
            }
            print(genre, [n for n, _ in games], dropped, idx, flush=True)
        print("live Qloo calls", qloo.live_calls)
    finally:
        await qloo.aclose()
        await store.close()
    llm = build_provider(s)
    if llm is not None:
        try:
            msg, _ = await complete_json(
                llm,
                [
                    {
                        "role": "user",
                        "content": "Estimate the percentage of each video game genre's players who are "
                        f"female: {', '.join(GENRES)}. Reply with JSON only: "
                        '{"female_percent": {"<genre>": <number>, ...}} with every genre exactly as written.',
                    }
                ],
                Shares,
                CallBudget(2),
                temperature=0.0,
                timeout=s.llm_timeout_seconds,
            )
            out["llm"] = {"model": model_name(s), "female_percent": msg.female_percent}
        finally:
            await llm.aclose()
    OUT.write_text(json.dumps(out, indent=1) + "\n")


def report() -> None:
    d = json.loads(OUT.read_text())
    names = list(GENRES)
    truth = [GENRES[g][0] for g in names]
    qloo = [d["genres"][g]["female"] for g in names]
    rho_q = spearman(qloo, truth)
    llm = d.get("llm")
    rho_l = spearman([llm["female_percent"].get(g, 0) for g in names], truth) if llm else None
    lines = [
        "# Audience check",
        "",
        "Does Qloo's audience skew match an independent survey? For 10 genres we compare Qloo's female index "
        "(`urn:demographics`, over- or under-index vs average) for a panel of well-known games with the female "
        f"share of each genre's players in Quantic Foundry's 2017 survey of about 270,000 gamers, as [reported by "
        f"Game Informer]({SOURCE}). The genres, panels and metric were fixed before any call. Qloo data collected "
        f"{d['collected']}; `apps/api/scripts/audience_check.py` regenerates this page.",
        "",
        f"**Spearman ρ between Qloo's female index and the survey: {rho_q:.3f}** (10 genres; Qloo orders "
        "them as the survey does, with only the survey's 69/69 tie split)."
        + (
            f" An LLM's guess of each share ({llm['model']}, no Qloo data): ρ {rho_l:.3f}."
            if llm and rho_l is not None
            else ""
        ),
        "",
        "| Genre | Survey: % female | Qloo female index | Qloo panel | LLM guess % |",
        "|---|---|---|---|---|",
    ]
    for g in sorted(names, key=lambda g: -GENRES[g][0]):
        row = d["genres"][g]
        guess = f"{llm['female_percent'].get(g, 'n/a')}" if llm else "n/a"
        lines.append(
            f"| {g} | {GENRES[g][0]:g} | {row['female']:+.2f} | {', '.join(row['games'])} | {guess} |"
        )
    lines += [
        "",
        "## Caveats",
        "",
        "- Ten genres, one survey. The survey is from 2017, self-selected, and Game Informer lists 10 of its 23 genres.",
        "- Qloo's index is relative to its average audience, not a share; only the order is compared.",
        "- The panels are a few famous games per genre, not the survey's own definition of each genre. Qloo "
        "found no match for "
        + ", ".join(n for g in names for n in d["genres"][g]["dropped"])
        + ", so those panels have two games.",
        "- An LLM may have read this survey; a match there is recall, not measurement. Qloo's index is measured "
        "for whatever comp set a studio picks, including combinations no survey covers.",
    ]
    (ROOT / "docs" / "audience-check.md").write_text("\n".join(lines) + "\n")
    web = {
        "collected": d["collected"],
        "source": SOURCE,
        "rho_qloo": round(rho_q, 3),
        "rho_llm": None if rho_l is None else round(rho_l, 3),
        "llm_model": llm["model"] if llm else None,
        "rows": [
            {
                "genre": g,
                "survey_female_pct": GENRES[g][0],
                "qloo_female_index": d["genres"][g]["female"],
            }
            for g in sorted(names, key=lambda g: -GENRES[g][0])
        ],
    }
    (ROOT / "apps" / "web" / "public" / "audience-check.json").write_text(
        json.dumps(web, indent=1) + "\n"
    )
    print(f"rho qloo {rho_q:.2f}", f"llm {rho_l:.2f}" if rho_l is not None else "")


if __name__ == "__main__":
    match sys.argv[1:]:
        case []:
            asyncio.run(collect())
            report()
        case ["report"]:
            report()
        case _:
            sys.exit(__doc__)
