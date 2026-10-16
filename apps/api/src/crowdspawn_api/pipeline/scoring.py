"""S3 ranking: spawn score = taste lift x platform fit x culture fit. Pure math over Qloo numbers.

All three factors are ratios around 1.0 with no tuned weights (docs/scenario-results.md compares them
against Google Trends truth for ten independent games):
- lift: comp-set fans vs all gamers in the city (taste over-index)
- platform fit: the game's platforms vs all gamers in the city (console-light markets drop for console games)
- culture fit: fans of the setting's films, shows and artists vs all gamers, relative to the average city
"""

from dataclasses import dataclass
from statistics import fmean

PLATFORMS = ("pc", "mobile", "console")


@dataclass(frozen=True)
class CityMetrics:
    target: float  # mean affinity_rank of comp-set fans in the city
    panels: dict[str, float]  # same for each platform's player panel
    cells: int
    culture: float | None = None  # same for fans of the culture anchors, if any

    @property
    def general(self) -> float:
        return fmean(self.panels.values())

    @property
    def lift(self) -> float:
        return self.target / self.general if self.general > 0 else 0.0

    def platform_fit(self, platforms: list[str]) -> float:
        if not platforms or self.general <= 0:
            return 1.0
        return fmean(self.panels[p] for p in platforms) / self.general


@dataclass(frozen=True)
class Score:
    score: float
    lift: float
    platform_fit: float
    culture_fit: float | None


def spawn_scores(metrics: dict[str, CityMetrics], platforms: list[str]) -> dict[str, Score]:
    culture_ratio = {
        k: m.culture / m.general
        for k, m in metrics.items()
        if m.culture is not None and m.general > 0
    }
    mean_culture = fmean(culture_ratio.values()) if culture_ratio else 0.0
    out = {}
    for k, m in metrics.items():
        cfit = culture_ratio[k] / mean_culture if k in culture_ratio and mean_culture > 0 else None
        pfit = m.platform_fit(platforms)
        out[k] = Score(
            score=m.lift * pfit * (cfit if cfit is not None else 1.0),
            lift=m.lift,
            platform_fit=pfit,
            culture_fit=cfit,
        )
    return out
