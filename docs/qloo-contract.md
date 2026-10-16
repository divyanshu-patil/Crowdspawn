# Qloo contract (verified live, 2026-10-16)

Everything here was recorded from live calls against `https://hackathon.api.qloo.com` with the `X-Api-Key` header. Raw responses live in `apps/api/tests/fixtures/qloo/` (keys stripped; heatmap and place fixtures trimmed to the fields we use). `scripts/spike_qloo.py` reproduces them (~127 calls).

## `GET /search`

| Param | Verified value |
|---|---|
| `query` | free text |
| `types` | `urn:entity:videogame` |
| `take` | int |

Response: `{"results": [{name, entity_id, types: [..], popularity, disambiguation: "YYYY-MM-DD, Developer", tags: [..], properties: {release_year, image: {url}, developer, ...}}]}`.
Quirks: the top hit is often a fuzzy neighbour ("Dispatch" → "The Dispatcher", "Hades" also returns "Hades Nebula"). We accept a hit only if `name_matches()` (normalised string, roman numerals → digits, SequenceMatcher ≥ 0.9).

## `GET /v2/insights`

Common: `signal.interests.entities` takes a **comma-separated** list of entity ids. `feature.explainability=true` adds per-signal contribution scores. `take` limits entities (ignored by heatmap).

Response for entity types: `{"success": true, "results": {"entities": [{name, entity_id, type: "urn:entity", subtype: "urn:entity:<type>", popularity, query: {affinity, explainability?: {"signal.interests.entities": [{entity_id, score}]}}, properties: {...}, tags: [...]}]}, "query": {explainability summary}}`.

| `filter.type` | Works with game signals? | Notes |
|---|---|---|
| `urn:entity:videogame` | yes | S2 expansion. `properties.audience_tags`, `emotional_tone`, `genre` are good "why" material |
| `urn:heatmap` | yes | needs `filter.location=POINT(lon lat)` + `filter.location.radius` (m). Returns `results.heatmap[{location:{latitude,longitude,geohash}, query:{affinity, affinity_rank, popularity}}]`, 400-3,100 cells per city |
| `urn:demographics` | yes | returns `results.demographics[{entity_id, query:{age:{24_and_younger,25_to_29,30_to_34,35_to_44,45_to_54,55_and_older}, gender:{male,female}}}]`, **one row per signal entity**; values are over/under-index deltas around 0, not shares |
| `urn:entity:artist`, `podcast`, `movie`, `brand` | yes | explainability per item |
| `urn:entity:place` | yes | only honours **`filter.location`**; `signal.location` is silently ignored (NYC request returned London/Paris) |
| `urn:entity:locality` | **no** | 400: "All of the provided signal.interests.entities were invalid" |

Location quirks:
- Heatmap `affinity` is rank-normalised **within** the request (min 0, max 1, mean exactly 0.5 for every city). It cannot compare cities. `affinity_rank` is comparable across requests (Hades: NYC 0.848, Tokyo 0.766).
- For artists, `signal.location` changes results (local flavour); `filter.location` is ignored silently (identical to global).
- Brands: not tested with location; we follow the doc and keep them global.

## `GET /v2/analysis/compare`

Params `a.signal.interests.entities`, `b.signal.interests.entities`, `take`. Response `{duration, results: {tags: [shared tags with query.score], a: [tags of A with query.count], b: [tags of B], matchEntities: []}}`. Gap view = tags in `b` not in `a` (target-only) and vice versa.

## Errors and limits

- Bad signals: HTTP 400 `{"errors": [{message, path}]}`.
- Rate limit: 5 rps (we use 4). Monthly: 10,000 calls. Phase 0 used ~140.
- Silent failures seen: `signal.location` on places and `filter.location` on artists return 200 with unfiltered results. Guards: heatmap cells must lie inside the requested radius; entity results must carry the requested `subtype`.

## Strategy decision for S3 (city score)

Two comp sets (cozy: Stardew Valley, Unpacking, A Short Hike; roguelike: Hades, Dead Cells, Slay the Spire) and a mainstream baseline (Minecraft, Fortnite, GTA V, Call of Duty: Warzone) across 15 cities.

| Metric (Spearman) | Heatmap `affinity_rank` mean | Place top-10 affinity mean |
|---|---|---|
| raw cozy vs baseline | -0.12 | **0.96** |
| raw rogue vs baseline | 0.15 | **0.98** |
| lift cozy vs lift rogue | 0.77 | -0.13 |
| lift spread | 0.93 - 1.67 | 0.98 - 1.02 |

Place affinity tracks the baseline almost perfectly (popularity) and its lifts are within ±3%, which is noise. Heatmap raw scores do not track the baseline, lifts spread widely, and the two comp sets rank cities differently (London #5 cozy vs #13 rogue; Austin #2 vs #3; Seattle top-5 only for rogue). **Decision: Strategy A, heatmap. City score = mean `affinity_rank` over all cells in the radius; lift = target / baseline.** The shared component (Tokyo on top for both) reflects "indie fans vs mainstream gamers", which is the over-indexing the product is about.

## Strategy update (2026-10-16): spawn score

Verified live on 33 cities. The 4-game mainstream baseline scored Tokyo 0.49 against 0.75-0.95 elsewhere, so every lift in Tokyo was inflated. Three player panels (PC: Counter-Strike 2, CS:GO, Valorant, Apex Legends, Rust, World of Tanks, PUBG, TF2; mobile: Clash Royale, Subway Surfers, PUBG Mobile, CoD Mobile, Candy Crush, Clash of Clans, Pokémon GO; console: Mario Kart 8 Deluxe, Zelda BotW, Smash Ultimate, Animal Crossing NH, God of War, Halo Infinite, Splatoon 3) put Tokyo at 0.80 average. PC and mobile panels rank countries alike; the console panel differs (Mexico, US, Canada high; Turkey, India, Poland low).

Culture anchors are resolved with `/search` per type (`urn:entity:movie`, `urn:entity:tv_show`, `urn:entity:artist`) and looked up with `/entities` (types come back in `types`, `subtype` is empty). Heatmaps accept them as `signal.interests.entities` like games. Indian anchors (Gully Boy, 3 Idiots, Arijit Singh): Delhi 0.82, Mumbai 0.90, Bengaluru 0.86, London 0.40, New York 0.30, Tokyo 0.30.

Spawn score = (target ÷ all-gamers) × (platform panels ÷ all-gamers) × ((culture ÷ all-gamers) ÷ mean over cities). Results against Google Trends: `docs/scenario-results.md`.

