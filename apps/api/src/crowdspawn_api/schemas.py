"""Public API models. Source of truth for openapi.json and packages/contracts."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Confidence = Literal["high", "medium", "low"]
PlanStatus = Literal["queued", "running", "done", "failed"]
PartnerType = Literal["artist", "podcast", "movie", "brand"]
Platform = Literal["pc", "mobile", "console"]


class Region(BaseModel):
    id: str
    name: str
    country: str
    lat: float
    lon: float
    radius_m: int
    default: bool = False
    languages: list[str] = []  # main languages to localise into: static reference data, not Qloo


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


class CultureSuggestion(BaseModel):
    name: str
    type: Literal["movie", "tv_show", "artist"]


class SuggestOut(BaseModel):
    suggestions: list[Suggestion]
    dropped: list[str]


class PlanIn(BaseModel):
    game: GameIn
    comp_entity_ids: list[str] = Field(min_length=1, max_length=5)
    culture_entity_ids: list[str] = Field(default=[], max_length=5)
    platforms: list[Platform] = Field(
        default=["pc", "mobile", "console"], min_length=1, max_length=3
    )
    regions: list[str] = Field(min_length=3, max_length=20)
    budget_usd: float | None = Field(default=None, gt=0, le=10_000_000)
    previous_game_entity_ids: list[str] = Field(default=[], max_length=5)
    mode: Literal["fast"] = "fast"

    @field_validator("comp_entity_ids", "culture_entity_ids", "platforms", "regions")
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


class CultureAnchor(BaseModel):
    entity_id: str
    name: str
    type: str
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
    score: float  # spawn score = lift x platform_fit x culture_fit; cities are ranked by it
    lift: float  # comp-set fans vs all gamers in the city
    platform_fit: float
    culture_fit: float | None = None
    target_score: float
    baseline_score: float  # all gamers: mean of the PC, mobile and console panels
    cells: int
    confidence: Confidence
    budget_share: float = 0.0
    budget_usd: float | None = None
    radius_m: int | None = None  # the heatmap radius Qloo scored
    languages: list[str] = []  # static reference table, not Qloo
    source: Literal["qloo"] = "qloo"
    result_ids: list[str]

    @model_validator(mode="before")
    @classmethod
    def _backfill(cls, data: Any) -> Any:
        """Plans saved before the spawn score was ranked by lift alone."""
        if isinstance(data, dict) and "score" not in data and "lift" in data:
            data = data | {"score": data["lift"], "platform_fit": 1.0}
        return data


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
    lift: float | None = None  # affinity / all gamers' affinity in the same place
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


class LLMPick(BaseModel):
    """A name an LLM suggested with no Qloo data, then looked up in Qloo."""

    name: str  # as the LLM wrote it
    entity_id: str | None = None  # None: Qloo found no entity of this type with a matching name
    qloo_name: str | None = None
    lift: float | None = None  # same lift as Qloo's partners: comp fans / all gamers
    image_url: str | None = None
    result_id: str | None = None


class LLMOnlyKind(BaseModel):
    kind: PartnerType
    picks: list[LLMPick]
    found: int  # picks Qloo could resolve
    median_lift: float | None  # over the found picks
    qloo_median_lift: float | None  # the plan's own global list, for comparison
    overlap: int  # picks also on the plan's global list


class LLMOnly(BaseModel):
    """What an LLM alone answers for the same inputs. A labelled baseline, never part of the plan."""

    plan_id: str
    provider: str
    model: str
    cities: list[str]  # region ids in the LLM's order, limited to the plan's candidates
    partners: list[LLMOnlyKind]


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


class HiddenMarket(BaseModel):
    """A city that ranks much higher for this game than for gamers in general."""

    region_id: str
    name: str
    rank: int  # by spawn score, 1-based
    gamer_rank: int  # by the all-gamers panels (baseline_score)


class Plan(BaseModel):
    id: str
    status: PlanStatus
    input: PlanIn
    comps: list[Comp] = []
    dropped_comps: list[str] = []
    culture: list[CultureAnchor] = []
    expanded: list[ExpandedGame] = []
    cities: list[City] = []
    hidden_markets: list[HiddenMarket] = []
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
    qloo_calls_left_today: int | None = None  # under QLOO_DAILY_CALL_CAP; None when there is no cap


# Region scout: what works in an area, and would my game work there.


class PlaceHit(BaseModel):
    entity_id: str
    name: str  # English or Latin-script name; Qloo often returns local script
    region: str  # Latin-script parents below country level, e.g. "Faro" or "Orange, California"
    lat: float
    lon: float


class PlatformMix(BaseModel):
    """Mean Qloo affinity_rank (0-1) of each platform's player panel in an area. An index, not a headcount."""

    pc: float
    mobile: float
    console: float
    general: float


class AreaActivity(BaseModel):
    id: str
    name: str
    country: str
    lat: float
    lon: float
    mix: PlatformMix


class ActivityOut(BaseModel):
    points: list[AreaActivity]
    skipped: list[str]
    calls: Calls


class ScoutAreaIn(BaseModel):
    lat: float = Field(ge=-60, le=75)
    lon: float = Field(ge=-180, le=180)
    radius_km: int = Field(default=40, ge=10, le=150)


class GenreHeat(BaseModel):
    genre: str
    lift: float  # genre panel heat / all gamers in the area
    examples: list[str]


class LocalGame(BaseModel):
    entity_id: str
    name: str
    affinity: float
    image_url: str | None = None


class ScoutArea(BaseModel):
    lat: float
    lon: float
    radius_km: int
    cells: int
    mix: PlatformMix
    genres: list[GenreHeat]
    games: list[LocalGame]
    source: Literal["qloo"] = "qloo"
    calls: Calls


class ScoutFitIn(ScoutAreaIn):
    comp_entity_ids: list[str] = Field(min_length=1, max_length=5)
    platforms: list[Platform] = Field(
        default=["pc", "mobile", "console"], min_length=1, max_length=3
    )


class ScoutFit(BaseModel):
    lat: float
    lon: float
    comps: list[str]
    lift: float
    platform_fit: float
    score: float
    verdict: Literal["strong", "promising", "neutral", "weak"]
    confidence: Confidence
    cells: int
    best_genre: GenreHeat | None = None
    source: Literal["qloo"] = "qloo"
    calls: Calls


class ScoutJudgeIn(ScoutAreaIn):
    title: str = Field(default="", max_length=80)
    description: str = Field(min_length=10, max_length=600)
    tags: list[str] = Field(default=[], max_length=8)
    platforms: list[Platform] = Field(
        default=["pc", "mobile", "console"], min_length=1, max_length=3
    )
    comp_entity_ids: list[str] = Field(default=[], max_length=5)  # optional: games the user picked
    # From a plan: when set (even empty), these and comp_entity_ids are the only names; the LLM proposes none.
    culture_entity_ids: list[str] | None = Field(default=None, max_length=5)


class RankedPlace(BaseModel):
    name: str
    score: float
    here: bool


class VerdictBand(BaseModel):
    verdict: str
    min_score: float  # lowest spawn score that earns this word at the result's confidence


class ScoutJudge(BaseModel):
    lat: float
    lon: float
    radius_km: int
    verdict: str  # a JUDGE_BANDS word, or "Common"
    bands: list[VerdictBand]  # the cut-offs for this confidence, highest first
    score: float
    lift: float
    platform_fit: float
    culture_fit: float | None
    confidence: Confidence
    cells: int
    comps: list[str]
    culture: list[str]
    dropped: list[str]  # names the LLM suggested that Qloo could not find
    ranking: list[RankedPlace]
    genres: list[GenreHeat]
    mix: PlatformMix
    games: list[LocalGame]
    summary: str
    summary_source: Literal["llm", "template"]
    model: str | None = None
    source: Literal["qloo"] = "qloo"
    calls: Calls


# Launch agent: an LLM that plans with Qloo tools, step by step.


class AgentIn(BaseModel):
    goal: str = Field(min_length=10, max_length=600)


class AgentStepOut(BaseModel):
    n: int
    thought: str
    tool: str
    args: dict[str, Any]
    observation: str
    ok: bool


class DraftGame(BaseModel):
    entity_id: str
    name: str


class DraftCulture(BaseModel):
    entity_id: str
    name: str
    type: str


class PlanDraft(BaseModel):
    """What the agent hands to a full launch plan (all Qloo entity ids)."""

    title: str
    description: str
    games: list[DraftGame]
    culture: list[DraftCulture]
    platforms: list[Platform]
    regions: list[str]


class AgentRun(BaseModel):
    id: str
    status: Literal["running", "done", "failed"]
    goal: str
    steps: list[AgentStepOut] = []
    answer: str | None = None
    answer_source: Literal["llm", "template"] | None = None
    draft: PlanDraft | None = None
    model: str | None = None
    error: Problem | None = None
    calls: Calls = Calls(live=0, cached=0)


class AskIn(BaseModel):
    plan: Plan  # the client sends the plan it shows, so saved sample plans work too
    question: str = Field(min_length=2, max_length=300)


class AskOut(BaseModel):
    """An answer written only from the plan's Qloo facts, checked like the brief."""

    answer: str
    grounded: bool  # False: the LLM's answer broke the grounding rules and was withheld
    provider: str
    model: str
