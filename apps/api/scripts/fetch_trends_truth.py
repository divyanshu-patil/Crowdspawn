"""Fetch scenario ground truth from Google Trends: interest by country, last 5 years, per analogue topic.

Not Qloo and never used by the app; only scripts/scenarios.py reads it. Writes scripts/trends_truth.json.
pytrends is unofficial and only needed here, so it is not a project dependency:
  uv run --no-project --with pytrends==4.9.2 --with "urllib3<2" python scripts/fetch_trends_truth.py
"""

import json
import time
from datetime import date
from pathlib import Path

from pytrends.request import TrendReq

HERE = Path(__file__).resolve().parent


def main() -> None:
    scenarios = json.loads((HERE / "scenarios.json").read_text())["scenarios"]
    trends = TrendReq(hl="en-US", tz=0)
    out: dict[str, object] = {"fetched": date.today().isoformat(), "timeframe": "today 5-y"}
    for s in scenarios:
        mid = s["truth"]["mid"]
        trends.build_payload([mid], timeframe="today 5-y")
        df = trends.interest_by_region(resolution="COUNTRY", inc_low_vol=False, inc_geo_code=True)
        out[s["id"]] = {
            row["geoCode"]: int(row[mid]) for _, row in df.iterrows() if int(row[mid]) > 0
        }
        print(s["id"], sorted(out[s["id"]].items(), key=lambda kv: -kv[1])[:8])  # type: ignore[union-attr]
        time.sleep(4)
    (HERE / "trends_truth.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
