"""Make one live Qloo call and save the raw response as a fixture.

Usage: uv run python scripts/record_fixture.py <path> <fixture-name> key=value [key=value ...]
Example: uv run python scripts/record_fixture.py /search search/hades query=Hades types=urn:entity:videogame
The API key is read from .env and never written to the fixture.
"""

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "qloo"


def env() -> dict[str, str]:
    out = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.split("#")[0].strip()
    return out


def call(path: str, params: dict[str, str]) -> tuple[int, object]:
    e = env()
    r = httpx.get(
        e.get("QLOO_BASE_URL", "https://hackathon.api.qloo.com") + path,
        params=params,
        headers={"X-Api-Key": e["QLOO_API_KEY"]},
        timeout=30,
    )
    try:
        body: object = r.json()
    except ValueError:
        body = {"_text": r.text[:2000]}
    return r.status_code, body


def save(name: str, path: str, params: dict[str, str], status: int, body: object) -> Path:
    out = FIXTURES / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"request": {"path": path, "params": params}, "status": status, "body": body},
                   indent=2, ensure_ascii=False)
    )
    return out


if __name__ == "__main__":
    path, name, *kv = sys.argv[1:]
    params = dict(p.split("=", 1) for p in kv)
    status, body = call(path, params)
    print(status, save(name, path, params, status, body).relative_to(ROOT))
    print(json.dumps(body, indent=1)[:3000])
