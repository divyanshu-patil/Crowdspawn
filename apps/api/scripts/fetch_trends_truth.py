"""Fetch scenario ground truth from Google Trends: interest by country, last 5 years, per analogue topic.

Not Qloo and never used by the app; only scripts/scenarios.py reads it. pytrends is unofficial and only
needed here, so it is not a project dependency:
  uv run --no-project --with pytrends==4.9.2 --with "urllib3<2" python scripts/fetch_trends_truth.py [scenarios file]

scenarios.json -> trends_truth.json, scenarios_holdout.json -> trends_truth_holdout.json. Scenarios already in
the output are kept, so a run cut short by Google's rate limit resumes where it stopped.

`... fetch_trends_truth.py --baseline` writes trends_baseline.json: interest in the topic "Video game"
(/m/01mw1) by country over the same window. scenarios.py divides by it for the over-index truth.
"""

import json
import sys
import time
from datetime import date
from pathlib import Path

from pytrends.request import TrendReq

HERE = Path(__file__).resolve().parent
BASELINE = "/m/01mw1"  # Google Trends topic "Video game"


def truth_file(scenarios: Path) -> Path:
    return scenarios.with_name(scenarios.name.replace("scenarios", "trends_truth"))


def by_country(trends: TrendReq, mid: str, label: str) -> dict[str, int]:
    for attempt in range(6):  # Google rate-limits pytrends often: back off politely
        try:
            trends.build_payload([mid], timeframe="today 5-y")
            df = trends.interest_by_region(
                resolution="COUNTRY", inc_low_vol=False, inc_geo_code=True
            )
            return {row["geoCode"]: int(row[mid]) for _, row in df.iterrows() if int(row[mid]) > 0}
        except Exception as e:  # pytrends raises plain ResponseError / TooManyRequestsError
            wait = 60 * 2**attempt
            print(label, f"failed ({type(e).__name__}), retrying in {wait}s", flush=True)
            time.sleep(wait)
    sys.exit(f"gave up on {label}; rerun later to resume")


def main() -> None:
    if sys.argv[1:] == ["--baseline"]:
        out = {
            "fetched": date.today().isoformat(),
            "timeframe": "today 5-y",
            "topic": "Video game",
            "mid": BASELINE,
            "interest": by_country(TrendReq(hl="en-US", tz=0), BASELINE, "baseline"),
        }
        (HERE / "trends_baseline.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
        print(sorted(out["interest"].items(), key=lambda kv: -kv[1])[:10])  # type: ignore[union-attr]
        return
    src = HERE / (sys.argv[1] if len(sys.argv) > 1 else "scenarios.json")
    dst = truth_file(src)
    scenarios = json.loads(src.read_text())["scenarios"]
    out: dict[str, object] = json.loads(dst.read_text()) if dst.exists() else {}
    out |= {"fetched": date.today().isoformat(), "timeframe": "today 5-y"}
    trends = TrendReq(hl="en-US", tz=0)
    for s in scenarios:
        if s["id"] in out:
            continue
        out[s["id"]] = by_country(trends, s["truth"]["mid"], s["id"])
        dst.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
        print(s["id"], sorted(out[s["id"]].items(), key=lambda kv: -kv[1])[:8], flush=True)  # type: ignore[union-attr]
        time.sleep(8)


if __name__ == "__main__":
    main()
