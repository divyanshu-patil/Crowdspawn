from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]

# Player panels for S3, resolved live on 2026-10-16. A city's "all gamers" score is the mean of the
# three; a game's platform fit is its platforms' mean over that. See docs/scenario-results.md.
PLATFORM_PANELS: dict[str, tuple[str, ...]] = {
    # Counter-Strike 2, CS:GO, Valorant, Apex Legends, Rust, World of Tanks, PUBG, Team Fortress 2
    "pc": (
        "1309CBC1-040A-4F17-8BD5-F70E99304C09",
        "C58AB791-E59B-4A20-8194-1DA91AFB9062",
        "38AE774E-F217-4C96-BE77-B3B40A6344E4",
        "B2344587-2AF4-4A4A-A018-5CCDE6E3B1A0",
        "68E25210-1EEB-492F-BB3C-18B4D43E3A28",
        "74DFAAA4-8F51-4215-905B-192010EAE4BF",
        "39CE4DC5-E089-4371-AC74-7A9D3FEFC973",
        "D5FAD200-F99E-4BA9-AF64-80D7C4682F8B",
    ),
    # Clash Royale, Subway Surfers, PUBG Mobile, Call of Duty Mobile, Candy Crush Saga, Clash of Clans, Pokemon GO
    "mobile": (
        "4713BB1F-44A9-4AE5-BFBF-0557B25A589A",
        "462D4F40-1097-4D97-9B08-4C2D2F8E6156",
        "7CF8323E-7B00-4522-A516-24BAA196F339",
        "329B6915-D27B-4EE2-8B82-4680A73B44EC",
        "766D99BD-60A0-4F50-AE4C-A1619A6E42B7",
        "A2EC9E00-10DB-43EF-A19D-CB60BF0BBCE3",
        "7127CE40-37EF-4C76-AA75-58D0C35E0749",
    ),
    # Mario Kart 8 Deluxe, Zelda: Breath of the Wild, Smash Ultimate, Animal Crossing: New Horizons,
    # God of War, Halo Infinite, Splatoon 3
    "console": (
        "43B2316E-1192-42BF-AAF7-78E06BADD771",
        "7E606158-8878-49D6-82AB-4C83A83F9974",
        "E2705C54-C0EF-4C16-AEF2-6D437A19CC9D",
        "08663BD2-E267-4C7F-9895-86410F67867C",
        "25B8D47A-4F85-4E8F-9CB1-75080FC4D986",
        "2D3274C5-B611-493B-91FE-E9626793D25A",
        "328D45B9-081D-4B94-8013-2E566E22CFDF",
    ),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_ROOT / ".env", extra="ignore")

    app_env: str = "development"  # development | test | production

    qloo_api_key: SecretStr = SecretStr("")
    qloo_base_url: str = "https://hackathon.api.qloo.com"
    qloo_rps: float = 4
    qloo_max_calls_per_run: int = 120
    qloo_cache_ttl_seconds: int = 86400
    qloo_timeout_seconds: float = 20

    llm_provider: str = "ollama_cloud"
    llm_timeout_seconds: float = 60
    llm_max_output_tokens: int = 1500
    llm_temperature: float = 0.2
    llm_max_calls_per_plan: int = 4

    ollama_base_url: str = "https://ollama.com"
    ollama_api_key: SecretStr = SecretStr("")
    ollama_model: str = ""

    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""
    openai_compat_base_url: str = ""
    openai_compat_api_key: SecretStr = SecretStr("")
    openai_compat_model: str = ""

    database_path: str = "./data/crowdspawn.sqlite3"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "info"
    plans_per_ip_per_hour: int = 10

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def db_file(self) -> Path:
        p = Path(self.database_path)
        return p if p.is_absolute() else API_ROOT / p


@lru_cache
def get_settings() -> Settings:
    return Settings()
