"""Public API models. Source of truth for openapi.json and packages/contracts."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Confidence = Literal["high", "medium", "low"]
PlanStatus = Literal["queued", "running", "done", "failed"]
PartnerType = Literal["artist", "podcast", "movie", "brand"]


class Region(BaseModel):
    id: str
    name: str
    country: str
    lat: float
    lon: float
    radius_m: int
    default: bool = False


class EntityOut(BaseModel):
    entity_id: str
    name: str
    type: str
    year: int | None = None
    image_url: str | None = None


class GameIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=600)
    tags: list[str] = Field(default=[], max_length=8)


class SuggestIn(GameIn):
    pass


class Suggestion(BaseModel):
    input_name: str
    resolved: EntityOut | None


class SuggestOut(BaseModel):
    suggestions: list[Suggestion]
    dropped: list[str]


class PlanIn(BaseModel):
    game: GameIn
    comp_entity_ids: list[str] = Field(min_length=1, max_length=5)
    regions: list[str] = Field(min_length=3, max_length=15)
    budget_usd: float | None = Field(default=None, gt=0, le=10_000_000)
    previous_game_entity_ids: list[str] = Field(default=[], max_length=5)
    mode: Literal["fast"] = "fast"

    @field_validator("comp_entity_ids", "regions")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("duplicates are not allowed")
        return v


class PlanCreated(BaseModel):
    id: str
    status: PlanStatus


class Comp(BaseModel):
    entity_id: str
    name: str
    image_url: str | None = None
    source: Literal["qloo"] = "qloo"
    result_id: str


class ExpandedGame(BaseModel):
    entity_id: str
    name: str
    affinity: float
    why: str
    image_url: str | None = None
    source: Literal["qloo"] = "qloo"
    result_id: str


class City(BaseModel):
    region_id: str
    name: str
    country: str
    lat: float
    lon: float
    lift: float
    target_score: float
    baseline_score: float
    cells: int
    confidence: Confidence
    budget_share: float = 0.0
    budget_usd: float | None = None
    source: Literal["qloo"] = "qloo"
    result_ids: list[str]


class Band(BaseModel):
    band: str
    index: float


class GenderSkew(BaseModel):
    label: str
    index: float


class Audience(BaseModel):
    age: list[Band]
    gender: list[GenderSkew]
    source: Literal["qloo"] = "qloo"
    result_id: str


class Partner(BaseModel):
    entity_id: str
    name: str
    affinity: float
    why: str
    city: str | None = None
    image_url: str | None = None
    source: Literal["qloo"] = "qloo"
    result_id: str


class Partners(BaseModel):
    artist: list[Partner] = []
    podcast: list[Partner] = []
    movie: list[Partner] = []
    brand: list[Partner] = []


class Gap(BaseModel):
    shared: list[str]
    target_only: list[str]
    studio_only: list[str]
    source: Literal["qloo"] = "qloo"
    result_id: str


class BriefSection(BaseModel):
    heading: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=1500)


class Brief(BaseModel):
    sections: list[BriefSection]
    source: Literal["llm", "template"]
    provider: str | None = None
    model: str | None = None
    notice: str | None = None


class Warning_(BaseModel):
    code: str
    message: str


class Calls(BaseModel):
    live: int
    cached: int


class Problem(BaseModel):
    code: str
    message: str


class Plan(BaseModel):
    id: str
    status: PlanStatus
    input: PlanIn
    comps: list[Comp] = []
    dropped_comps: list[str] = []
    expanded: list[ExpandedGame] = []
    cities: list[City] = []
    audience: Audience | None = None
    partners: Partners = Partners()
    gap: Gap | None = None
    brief: Brief | None = None
    warnings: list[Warning_] = []
    limits: list[str] = []
    error: Problem | None = None
    created_at: str
    calls: Calls = Calls(live=0, cached=0)


class TraceRow(BaseModel):
    result_id: str
    step: str
    endpoint: str
    params: dict[str, str]
    cache_hit: bool
    status: int
    duration_ms: int
    at: str


class LLMStatus(BaseModel):
    provider: str
    model: str
    status: Literal["configured", "unconfigured"]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    qloo: Literal["ok", "unconfigured", "error"]
    llm: LLMStatus
    version: str
