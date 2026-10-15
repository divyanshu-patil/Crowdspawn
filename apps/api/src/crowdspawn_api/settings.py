from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]

# Mainstream games used as the S3 baseline (resolved live in Phase 0):
# Minecraft, Fortnite, Grand Theft Auto V, Call of Duty: Warzone.
BASELINE_ENTITY_IDS = (
    "CDBDE254-71F0-4640-8D04-5373BEAE5278",
    "B335BB51-7158-4C34-89D1-4F1DB7CB5C01",
    "FEFD4E0D-D8F2-4BF9-86C9-06949DE82BCD",
    "B9318203-796E-4327-B161-5EEC584C382F",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_ROOT / ".env", extra="ignore")

    app_env: str = "development"  # development | test | production

    qloo_api_key: SecretStr = SecretStr("")
    qloo_base_url: str = "https://hackathon.api.qloo.com"
    qloo_rps: float = 4
    qloo_max_calls_per_run: int = 60
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
