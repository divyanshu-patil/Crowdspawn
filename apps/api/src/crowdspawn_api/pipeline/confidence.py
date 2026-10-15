"""City confidence labels. Thresholds are shown to users in the UI tooltip; keep them in sync.

- cells: number of heatmap cells Qloo returned for the city (sample size; live runs give 30-400).
- margin: |lift - 1|, how far the city sits from ordinary gamer interest (effect size).
"""

from ..schemas import Confidence

HIGH_CELLS, HIGH_MARGIN = 150, 0.10
MEDIUM_CELLS, MEDIUM_MARGIN = 50, 0.03


def confidence(lift: float, cells: int) -> Confidence:
    margin = round(abs(lift - 1), 6)  # 0.9 must count as a 0.10 margin, not 0.0999...
    if cells >= HIGH_CELLS and margin >= HIGH_MARGIN:
        return "high"
    if cells >= MEDIUM_CELLS and margin >= MEDIUM_MARGIN:
        return "medium"
    return "low"
