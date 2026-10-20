"""Fetch scenario ground truth from Google Trends: interest by country, last 5 years, per analogue topic.

Not Qloo and never used by the app; only scripts/scenarios.py reads it. pytrends is unofficial and only
needed here, so it is not a project dependency:
  uv run --no-project --with pytrends==4.9.2 --with "urllib3<2" python scripts/fetch_trends_truth.py [scenarios file]

scenarios.json -> trends_truth.json, scenarios_holdout.json -> trends_truth_holdout.json. Scenarios already in
the output are kept, so a run cut short by Google's rate limit resumes where it stopped.
"""

import json
import sys
import time
from datetime import date
from pathlib import Path

from pytrends.request import TrendReq

HERE = Path(__file__).resolve().parent


def truth_file(scenarios: Path) -> Path:
    return scenarios.with_name(scenarios.name.replace("scenarios", "trends_truth"))


def main() -> None:
    src = HERE / (sys.argv[1] if len(sys.argv) > 1 else "scenarios.json")
    dst = truth_file(src)
    scenarios = json.loads(src.read_text())["scenarios"]
    out: dict[str, object] = json.loads(dst.read_text()) if dst.exists() else {}
    out |= {"fetched": date.today().isoformat(), "timeframe": "today 5-y"}
    trends = TrendReq(hl="en-US", tz=0)
    for s in scenarios:
        if s["id"] in out:
            continue
        mid = s["truth"]["mid"]
        for attempt in range(6):  # Google rate-limits pytrends often: back off politely
            try:
                trends.build_payload([mid], timeframe="today 5-y")
                df = trends.interest_by_region(
                    resolution="COUNTRY", inc_low_vol=False, inc_geo_code=True
                )
                break
            except Exception as e:  # pytrends raises plain ResponseError / TooManyRequestsError
                wait = 60 * 2**attempt
                print(s["id"], f"failed ({type(e).__name__}), retrying in {wait}s", flush=True)
                time.sleep(wait)
        else:
            sys.exit(f"gave up on {s['id']}; rerun later to resume")
        out[s["id"]] = {
            row["geoCode"]: int(row[mid]) for _, row in df.iterrows() if int(row[mid]) > 0
        }
        dst.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
        print(s["id"], sorted(out[s["id"]].items(), key=lambda kv: -kv[1])[:8], flush=True)  # type: ignore[union-attr]
        time.sleep(8)


if __name__ == "__main__":
    main()
