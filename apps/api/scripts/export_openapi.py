"""Write apps/api/openapi.json from the FastAPI app (source for packages/contracts)."""

import json
from pathlib import Path

from crowdspawn_api.main import create_app
from crowdspawn_api.settings import Settings

out = Path(__file__).resolve().parents[1] / "openapi.json"
spec = create_app(Settings(_env_file=None)).openapi()  # type: ignore[call-arg]
out.write_text(json.dumps(spec, indent=2) + "\n")
print(f"wrote {out.name} ({len(spec['paths'])} paths)")
