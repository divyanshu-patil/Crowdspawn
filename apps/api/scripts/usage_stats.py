"""Count plans and agent runs per UTC day, distinct plan titles and live Qloo calls, from SQLite (J21).

Usage: uv run python scripts/usage_stats.py [database.sqlite3] [--since YYYY-MM-DD]

Run it against the deployed database so any "N plans run" statement is true. Use --since to leave out
development days. Nothing here identifies a visitor: no IP addresses are stored, and none are read.
"""

import json
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from crowdspawn_api.settings import get_settings


def day(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).date().isoformat()


def stats(db: Path, since: str = "") -> str:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        plans = [
            (day(t), s, json.loads(i))
            for t, s, i in con.execute("SELECT created_at, status, input FROM plans")
        ]
        runs = [(day(t), s) for t, s in con.execute("SELECT created_at, status FROM runs")]
        calls = dict(con.execute("SELECT day, calls FROM qloo_daily").fetchall())
    finally:
        con.close()
    plans = [p for p in plans if p[0] >= since]
    runs = [r for r in runs if r[0] >= since]
    days = sorted({d for d, *_ in plans} | {d for d, _ in runs} | {d for d in calls if d >= since})
    p_all, p_done = Counter(d for d, *_ in plans), Counter(d for d, s, _ in plans if s == "done")
    r_all, r_done = Counter(d for d, _ in runs), Counter(d for d, s in runs if s == "done")
    titles = {p["game"]["title"].strip().lower() for _, s, p in plans if s == "done"}
    lines = [
        f"Usage{f' since {since}' if since else ''}: {len(plans)} plans ({sum(p_done.values())} done), "
        f"{len(runs)} agent runs ({sum(r_done.values())} done), {len(titles)} distinct titles among done plans.",
        "",
        "| Day (UTC) | Plans (done) | Agent runs (done) | Live Qloo calls |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {d} | {p_all[d]} ({p_done[d]}) | {r_all[d]} ({r_done[d]}) | {calls.get(d, '-')} |"
        for d in days
    ]
    lines.append("")
    lines.append("Live Qloo calls are counted only where QLOO_DAILY_CALL_CAP is on (production).")
    return "\n".join(lines)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--since")]
    since = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--since=")), "")
    if "--since" in sys.argv:
        since = sys.argv[sys.argv.index("--since") + 1]
        args = [a for a in args if a != since]
    print(stats(Path(args[0]) if args else get_settings().db_file, since))
