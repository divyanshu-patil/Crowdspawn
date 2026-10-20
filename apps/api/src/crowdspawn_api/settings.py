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

# Genre panels for the region scout (resolved live on 2026-10-16): genre heat in an area vs all gamers.
GENRE_PANELS: dict[str, tuple[tuple[str, str], ...]] = {
    "Open-world action": (
        ("Grand Theft Auto V", "FEFD4E0D-D8F2-4BF9-86C9-06949DE82BCD"),
        ("Red Dead Redemption 2", "0ED6691B-1F06-46D7-8F17-DB18826A5D0F"),
        ("Cyberpunk 2077", "2575A4C0-5459-42E9-B119-FE7CFC8D558B"),
        ("Assassin's Creed Valhalla", "7560E1A0-A959-4A92-8412-3E49C9A820ED"),
    ),
    "Battle royale": (
        ("Fortnite", "B335BB51-7158-4C34-89D1-4F1DB7CB5C01"),
        ("Call of Duty: Warzone", "B9318203-796E-4327-B161-5EEC584C382F"),
        ("Fall Guys", "89C8B166-CDE5-45C6-A471-FA286F21FD8D"),
        ("Garena Free Fire: Rampage", "B75FDF68-3EC7-4018-918E-213A83BF757B"),
    ),
    "MOBA": (
        ("League of Legends", "8E474FED-3ACD-46B1-A51C-C28B9FA206B1"),
        ("Dota 2", "75CC5D15-CDE1-4AE8-91C6-5A2BCDA06EA6"),
        ("Mobile Legends: Bang bang", "2B118A8C-1B97-4475-BB1B-DE947727ACD3"),
        ("Arena of Valor", "E54A8C29-D090-4366-AA8D-F2590B5CCBBA"),
    ),
    "Sports": (
        ("EA Sports FC 24", "2108A362-6EF1-4A64-8404-FDEB9FFA517F"),
        ("NBA 2K24", "59C0B1C4-5065-4B51-8421-4B877B921A30"),
        ("Rocket League", "E946C4F4-7E23-4CD4-A2FD-92255F0E33A2"),
    ),
    "Racing": (
        ("Forza Horizon 5", "96F4FBF7-6C08-436A-9C97-155FF6344994"),
        ("Gran Turismo 7", "7B763E10-9939-4979-BB76-F4F74AC87220"),
        ("Need for Speed Heat", "1BCD980C-D4B9-4CA6-AC31-B65F3C94FF90"),
        ("Asphalt 9: Legends", "81114ECA-8AFE-4F9A-B463-766B0A459C89"),
    ),
    "Anime and JRPG": (
        ("Persona 5", "C5FBF982-EA78-42C7-A6F7-BEC4835EF5F4"),
        ("Final Fantasy VII Remake", "7292C020-0335-4A7A-B9F6-F3F0E6D4D604"),
        ("Genshin Impact", "DE584C3E-25B7-4B25-9BD8-30A12D4B686F"),
    ),
    "Soulslike": (
        ("Elden Ring", "46CBADC5-F4A6-4E97-93B2-959066C9F608"),
        ("Dark Souls III", "CC75C37E-7CD0-47E0-8707-ABEFF5CE9891"),
        ("Sekiro: Shadows Die Twice", "08910533-E760-4683-9201-57B9B73A4F7F"),
        ("Black Myth: Wukong", "A7219D10-2E8D-417C-A93D-CC79A01DFD71"),
    ),
    "Cozy and life sim": (
        ("Stardew Valley", "875DB771-9C4C-4DD0-9249-D2ABD95711F1"),
        ("The Sims 4", "2225FC45-A2BE-454C-8527-6EAF3F4BF3DB"),
        ("Unpacking", "97B46B79-891A-4580-A0F8-C1CC34F3EFF6"),
        ("Spiritfarer", "522A4716-0A5A-4A97-B4A7-CA13ACA36C11"),
    ),
    "Roguelike": (
        ("Hades", "BA00D00A-E4CD-48C0-A22E-CFC52039D618"),
        ("Dead Cells", "870FBF81-80F8-401A-9621-63DBF6AB6C07"),
        ("Slay the Spire", "20BEE4A4-44C1-49CC-962D-CC0B4EE80102"),
        ("Vampire Survivors", "E37DE35F-A21F-4AA1-B730-7FCF6721E253"),
    ),
    "Strategy": (
        ("Age of Empires III", "EEF6756A-366A-48E7-A346-DCFB2624381B"),
        ("Sid Meier's Civilization VI", "0D2F4F91-7B41-4261-AEE1-58EDE1C95559"),
        ("Crusader Kings III", "F8F3FCD6-DB46-4132-9A58-CF1C59687A7B"),
        ("Total War: WARHAMMER III", "F7787FF0-716C-4706-BA28-2D59C39162C7"),
    ),
    "Survival and crafting": (
        ("Minecraft", "CDBDE254-71F0-4640-8D04-5373BEAE5278"),
        ("Valheim", "4C8A2AB2-B8F8-4FDE-B2CA-785586AC4D8A"),
        ("Terraria", "FE25ADF3-767A-405B-9DC3-69D52BC8C185"),
        ("ARK: Survival Evolved", "0299CDEC-99EF-43F8-83E9-7E78A40C086E"),
    ),
    "Horror": (
        ("Resident Evil Village", "32B46B33-1104-4F8A-B946-6E78C63F5593"),
        ("Five Nights at Freddy's", "F10F4D06-F9DF-4093-AF3C-AC647E26762E"),
        ("Phasmophobia", "82ED7F95-5D9E-4E9E-A88A-C98FDF0142C9"),
        ("Dead by Daylight", "FFF75371-964C-4393-8AF1-A7F731E91B39"),
    ),
    "Fighting": (
        ("Tekken 7", "C2C94315-C4B5-47B7-8476-D36D369DF929"),
        ("Street Fighter 6", "85FCB0FC-4EDC-409A-912B-85AC1E74E065"),
        ("Mortal Kombat 11", "403B7A89-9783-4B6D-8D85-01C96F48EB04"),
        ("Dragon Ball FighterZ", "97B0D6AE-248B-415D-BDEA-9A7953FD8B33"),
    ),
    "Simulation": (
        ("Euro Truck Simulator 2", "E1C3D578-D7D7-4733-8D89-C0F7777D6C01"),
        ("Farming Simulator 22", "4D7B6677-69F6-4805-834A-F80393850EFF"),
        ("Microsoft Flight Simulator", "A46ACA02-38D7-4624-92FE-639196FC0C5A"),
        ("Cities: Skylines", "01BD171B-1C78-4338-9269-CE8BEB5843FF"),
    ),
    "MMORPG": (
        ("World of Warcraft", "6BED0640-B460-42CA-8C10-290BD2B1F690"),
        ("Final Fantasy XIV Online", "556B37E1-FBD4-4F1E-B25B-C8166F951499"),
        ("Lost Ark", "709CC992-3940-4E58-94AE-A1103BFE9CB2"),
        ("Black Desert Online", "3D4094DE-3AE0-4347-955A-B69CE135AE3A"),
    ),
}
PANEL_TTL_SECONDS = 7 * 86400  # panels describe whole markets; they change slowly


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_ROOT / ".env", extra="ignore")

    app_env: str = "development"  # development | test | production

    qloo_api_key: SecretStr = SecretStr("")
    qloo_base_url: str = "https://hackathon.api.qloo.com"
    qloo_rps: float = 4
    qloo_max_calls_per_run: int = 120
    qloo_cache_ttl_seconds: int = 86400
    qloo_timeout_seconds: float = 20
    # Live Qloo calls per UTC day across all users (cache hits are free). Unset: 400 in production,
    # off elsewhere; 0 turns it off.
    qloo_daily_call_cap: int | None = None

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
    scouts_per_ip_per_hour: int = 60

    @property
    def daily_cap(self) -> int:
        if self.qloo_daily_call_cap is not None:
            return self.qloo_daily_call_cap
        return 400 if self.app_env == "production" else 0

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
