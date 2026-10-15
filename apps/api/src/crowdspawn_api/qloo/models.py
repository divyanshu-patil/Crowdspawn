"""Qloo response models, built from the Phase 0 fixtures (see docs/qloo-contract.md)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _M(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Tag(_M):
    name: str = ""  # live: some tags (urn:tag:voice_type:qloo) carry no name
    tag_id: str | None = None
    id: str | None = None


class SearchHit(_M):
    name: str
    entity_id: str
    types: list[str] = []
    popularity: float | None = None
    disambiguation: str | None = None
    properties: dict[str, Any] = {}

    @property
    def year(self) -> int | None:
        y = self.properties.get("release_year")
        return int(y) if isinstance(y, int) else None

    @property
    def image_url(self) -> str | None:
        img = self.properties.get("image") or {}
        return img.get("url") if isinstance(img, dict) else None


class SearchResponse(_M):
    results: list[SearchHit] = []


class Contribution(_M):
    entity_id: str
    score: float


class EntityQuery(_M):
    affinity: float | None = None
    explainability: dict[str, list[Contribution]] = {}


class Entity(_M):
    name: str
    entity_id: str
    subtype: str | None = None
    types: list[str] = []
    popularity: float | None = None
    query: EntityQuery = EntityQuery()
    properties: dict[str, Any] = {}
    tags: list[Tag] = []

    @property
    def contributions(self) -> list[Contribution]:
        return self.query.explainability.get("signal.interests.entities", [])

    @property
    def image_url(self) -> str | None:
        img = self.properties.get("image") or {}
        return img.get("url") if isinstance(img, dict) else None


class EntityResults(_M):
    entities: list[Entity] = []


class EntityInsights(_M):
    results: EntityResults = EntityResults()


class LookupResponse(_M):
    results: list[Entity] = []


class Location(_M):
    latitude: float
    longitude: float


class HeatmapQuery(_M):
    affinity: float
    affinity_rank: float
    popularity: float | None = None


class HeatmapCell(_M):
    location: Location
    query: HeatmapQuery


class HeatmapResults(_M):
    heatmap: list[HeatmapCell] = []


class HeatmapInsights(_M):
    results: HeatmapResults = HeatmapResults()


class DemoQuery(_M):
    age: dict[str, float] = {}
    gender: dict[str, float] = {}


class DemoRow(_M):
    entity_id: str | None = None
    query: DemoQuery


class DemoResults(_M):
    demographics: list[DemoRow] = []


class DemographicsInsights(_M):
    results: DemoResults = DemoResults()


class CompareTag(_M):
    name: str
    tag_id: str | None = None
    subtype: str | None = None
    query: dict[str, Any] = {}


class CompareResults(_M):
    tags: list[CompareTag] = []
    a: list[CompareTag] = []
    b: list[CompareTag] = []


class CompareResponse(_M):
    results: CompareResults = Field(default_factory=CompareResults)
