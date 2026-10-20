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

## Region scout calls (verified live 2026-10-16)

- `/search` with `types=urn:entity:locality` geocodes places: each result has top-level `location: {lat, lon}` and a `disambiguation` such as "Lagos, Nigeria". Non-Latin names come back in local script ("Київ").
- `/v2/insights` with `filter.type=urn:entity:videogame` honours **`signal.location`** + `signal.location.radius`: Delhi returns PUBG, Minecraft, CoD Mobile, Clash of Clans, Free Fire; Tokyo returns Hello Kitty, Animal Crossing Pocket Camp, Naruto, Ys VIII. Without any signal it returns 400.
- `urn:heatmap` works at any point with data (Lagos: 604 cells); open sea or empty land returns no cells, which the scout reports as `no_area_data` after widening the radius once.
- Genre panels (15 × 3-4 games) and the activity snapshot for 67 cities are cached for 7 days.

## Partner lift (verified live 2026-10-20, J11)

14 calls, saved in `apps/api/tests/fixtures/qloo/partners_lift/` (q01–q14; comps Hades, Stardew Valley and Celeste unless noted).

- **(a) Is entity `query.affinity` comparable across requests?** Partly. It is a 0–1 score, but not rank-normalised per request the way heatmap `affinity` is: the same artist gets the same affinity at `take=10` and `take=50` (q01 vs q02), and different signals give different ranges (comps 0.911–0.940, all-gamers 0.910–0.929 for artists). There is no rank field. `query` also carries `measurements.audience_growth`.
- **(b) Does an all-gamers request share enough entities?** Not without help. Top-50 overlap with the comp list was 0 of 50 for artists and movies, 8 for podcasts and 43 for brands (q01/q03, q04/q05, q06/q07, q11/q12). **`filter.entities=<ids>`** solves it: with the all-gamers signal (union of the 21 `PLATFORM_PANELS` ids) it returns exactly the requested ids with their affinity (q13). `filter.results.entities` behaves identically (q14). The docs describe `filter.entities` as "often used to assess the affinity of an entity towards input".
- **(c) Popularity and location parameters.** `filter.popularity.max=0.9` works for artists (q10: highest popularity returned 0.891, against 0.996 unfiltered). No location-weighting parameter is documented. `signal.location` with `signal.location.radius` changes the list (q08 Istanbul vs q01 global share 1 of 50). `bias.trends` is documented only for "select categories" and was not tested.
- **Method used.** Lift = comp-signal affinity ÷ all-gamers affinity for the same ids in the same place. Each list is Qloo's top 30 by comp affinity, re-ranked by lift (8 global, 4 per city). Lifts are small (1.03–1.27) because both are affinities near 1. Ranking by lift demotes names every gamer likes, such as game-studio sound teams and 100 gecs (q01/q13), and keeps names specific to these fans. It costs one extra call per list: 26 instead of 13 per plan.

## Scoring names an LLM suggests (verified live 2026-10-21)

- **`/search` with `types=urn:entity:podcast` and `types=urn:entity:brand` works** like the other types: "The Joe Rogan Experience" and "Red Bull" each come back first with the requested type.
- **`filter.entities` works with a comp signal too**, not only the all-gamers one: `signal.interests.entities=<Stardew Valley>` with `filter.entities=<Taylor Swift>` returns exactly that artist and its affinity (0.837).
- **Method:** the LLM-only comparison resolves each name the LLM suggests (search, same type, name must match), then scores the resolved ids with the same lift as Qloo's own partners: comp-signal affinity ÷ all-gamers affinity, two calls per type. Names Qloo can't resolve are shown as "not found in Qloo", never scored.
