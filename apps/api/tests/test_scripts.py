"""Offline scripts: studio validation (J20) and usage stats (J21), on synthetic data."""

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import studio_validation  # noqa: E402
import usage_stats  # noqa: E402


def plan(cities: list[tuple[str, float]]) -> dict[str, Any]:
    return {
        "input": {"game": {"title": "Long Haul"}},
        "cities": [{"country": c, "score": s} for c, s in cities],
    }


def test_studio_validation_scores_countries_as_the_mean_of_their_cities(tmp_path: Path) -> None:
    p = plan([("TR", 1.3), ("PL", 1.2), ("PL", 1.0), ("DE", 1.05), ("US", 0.9), ("JP", 0.8)])
    csv = tmp_path / "wishlists.csv"
    csv.write_text("country_code,value\npl,900\nTR,500\nDE,400\nUS,300\nJP,100\nFR,50\n")
    values = studio_validation.read_values(csv)
    assert values["PL"] == 900 and studio_validation.country_scores(p)["PL"] == pytest.approx(1.1)
    md = studio_validation.report(p, values)
    assert "| Studio's #1 country | PL |" in md
    assert "| Crowdspawn's top 3 | TR, PL, DE |" in md
    assert "| Studio's #1 is our #1 | no |" in md and "| Studio's #1 is in our top 3 | yes |" in md
    assert "| Spearman ρ | 0.9 |" in md and "compared (5)" in md  # FR is not in the plan


def test_studio_validation_rejects_a_csv_without_the_header(tmp_path: Path) -> None:
    csv = tmp_path / "bad.csv"
    csv.write_text("Country,Wishlists\nPoland,900\n")
    with pytest.raises(SystemExit, match="country_code,value"):
        studio_validation.read_values(csv)


async def test_usage_stats_counts_per_day_and_distinct_titles(tmp_path: Path) -> None:
    from crowdspawn_api.storage import Store

    db = tmp_path / "u.sqlite3"
    store = await Store.open(db)
    try:
        for i, title in enumerate(["Long Haul", "long haul ", "Moss Hollow"]):
            await store.create_plan(f"p{i}", {"game": {"title": title}})
            await store.set_status(f"p{i}", "done", result={})
        await store.create_plan("p9", {"game": {"title": "Broken"}})
        await store.create_run("a1", {"goal": "cozy farming game"})
        await store.take_daily_call(400)
    finally:
        await store.close()
    out = usage_stats.stats(db)
    assert "4 plans (3 done), 1 agent runs (0 done), 2 distinct titles" in out
    assert "| 4 (3) | 1 (0) | 1 |" in out
    assert "0 plans" in usage_stats.stats(db, since="2999-01-01")
