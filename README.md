# Crowdspawn

**Find where your players already are, and who else they love, before launch day.**

Crowdspawn gives indie game studios a launch plan built from [Qloo Taste AI](https://qloo.com) data: the cities where fans of comparable games over-index against mainstream gamers, the audience's age and gender skew, the artists, podcasts, films and brands those fans love, and a budget split. An LLM writes the brief from that data only, and every claim links back to the Qloo call that produced it.

Built for the Qloo Agentic Hackathon 2026.

![A Crowdspawn launch plan: spawn map and ranked cities](docs/screenshots/plan.png)

## Quick start

Requirements: Node 24+, pnpm 11, [uv](https://docs.astral.sh/uv/) (Python 3.12 is fetched by uv).

```sh
pnpm install          # also runs `uv sync` for the API (postinstall)
cp apps/api/.env.example apps/api/.env          # then fill in QLOO_API_KEY and OLLAMA_API_KEY
cp apps/web/.env.example apps/web/.env.local
pnpm dev              # starts web (http://localhost:3000) and API (http://localhost:8000) together
```

`/sample` works with no keys at all. Without `OLLAMA_API_KEY` plans still work and the brief falls back to a grounded template. Without `QLOO_API_KEY` no plan is produced (see the kill-switch test).

| Command | What it does |
|---|---|
| `pnpm dev` | Web + API with hot reload (`turbo run dev`) |
| `pnpm test` | API pytest (fixtures, no network, coverage gate 80%) + web Vitest |
| `pnpm lint` / `pnpm check-types` | ruff + ESLint / mypy --strict + tsc |
| `pnpm build` | Exports `openapi.json` and builds the Next.js app |
| `pnpm contracts` | Regenerates `packages/contracts` TypeScript types from the API |
| `pnpm --filter api test:live` | One live smoke test against real Qloo (spends a few calls) |

## Region scout (`/scout`)

A second tool for the other question: *what works in a place?* A pixel-tile world map with real country borders, shaded by each country's Qloo **gamer taste match** (0-100: mean affinity rank of PC, console and mobile hit-game panels in its main cities; a taste score, not a player count, since Qloo has no player counts). Hover a country to see its readings; click anywhere (or search a town through Qloo locality search) to drop an area-select ring and get:

- **Genres that over-index there:** 15 genre panels (3-4 well-known games each) scored against all gamers in the area.
- **Games locals love:** Qloo video game insights with `signal.location`.
- **Will my game work here?** Describe your game. An LLM proposes comparable games and the culture it draws on (names only); Qloo resolves each one and scores the spot against 8 reference cities with the plan's spawn score (taste × platform × culture). You get a loot-rarity verdict (Legendary, Epic, Rare, Uncommon, Common) with an estimated probability that players there over-index for your game (capped at 3-97% and pulled toward 50% when confidence is low; a model estimate, not sales odds), the ranking, top genres, local favourites and a short explanation whose numbers are checked against the facts.
- **50 popular places** (New York, London, Tokyo, Lagos, Jakarta and more) are pre-scouted into a bundled Qloo snapshot (`apps/api/scripts/snapshot_scout.py`), so they answer instantly with no calls.

Areas with no Qloo cells widen to 120 km, then snap to the nearest city with a reading. Panels are cached for a week; a new area costs about 19 calls.

## Feel

Sketchpad grid squares rise into 3D blocks under the mouse (only where nothing sits on top of them). Sound effects are 8-bit blips synthesized at runtime with the Web Audio API, so there are no audio files and nothing to license; the nav toggle mutes them and remembers the choice.

## Architecture

```
Browser (Next.js 16, apps/web)
   |  fetch + Server-Sent Events          no keys ever reach the browser
   v
FastAPI (apps/api)
   |-- routes --> orchestrator S1..S8 ---- progress events --> SQLite event log --> SSE
   |       |-- QlooClient --(X-Api-Key)--> hackathon.api.qloo.com
   |       |       token bucket (4 rps), retries, SQLite cache, per-run call cap, call trace
   |       '-- LLMProvider --> Ollama Cloud | Gemini | any OpenAI-compatible | Fake
   '-- SQLite: plans, events, traces, cache
packages/contracts: TS types generated from apps/api/openapi.json
```

## The Qloo call chain

Each step depends on the one before it. All parameters were verified live and recorded in [`docs/qloo-contract.md`](docs/qloo-contract.md).

| Step | Qloo call | Output |
|---|---|---|
| S1 Resolve comps and culture | `/entities` (plan) or `/search` (picker, LLM suggestions) | Real Qloo video game ids, plus optional culture anchors (films, shows, artists of the game's setting); unknown names are dropped, never invented |
| S2 Expand | `/v2/insights` `filter.type=urn:entity:videogame` + explainability | 20 similar games with the comps that drive each one |
| S3 Cities | `urn:heatmap` per city for the comp set, PC, mobile and console player panels, and the culture anchors | **Spawn score = taste lift × platform fit × culture fit** (all ratios of mean `affinity_rank`), with confidence |
| S4 Audience | `urn:demographics` | Age and gender over/under-index |
| S5 Partners | `/v2/insights` for artist, podcast, movie, brand (+ `signal.location` for the top 3 cities) | Partners with affinity and Qloo's reasons |
| S6 Gap (optional) | `/v2/analysis/compare` | Tastes shared with your last game vs new ground |
| S7 Budget | none, deterministic | Split by spawn score × confidence, sums to exactly 100% |
| S8 Brief | none, LLM over S1–S7 facts | Prose that cites `[q12]` result ids; validated before display |

A plan with 5 comps, 4 culture anchors and 18 cities uses about 107 Qloo calls; the player panels are shared across plans and cached, so a new plan usually costs about 2 live calls per city, and 0 on repeat.

### Why it can't exist without Qloo (the swap test)

Every city, entity, score and audience figure carries `source: "qloo"` and a `result_id` in the trace (tested: Q1). The LLM only suggests comp *names* (which Qloo must resolve) and words the brief. A grounding validator rejects any city, bold name, number or citation not present in the Qloo results, regenerates once, then falls back to a template (L7).

**Kill-switch test:** with `QLOO_API_KEY` empty or wrong, a plan ends `failed` with `qloo_unconfigured` / `qloo_auth`, no cities or brief are produced, and no LLM call is made (`tests/test_api.py::test_kill_switch_*`, and the error screen in the UI).

**LLM-swap test:** switching `LLM_PROVIDER` between `ollama_cloud`, `gemini`, `openai_compat` and `fake` changes only the brief; the rest of the plan JSON is identical (`test_provider_swap_changes_only_brief`). Only `apps/api/src/crowdspawn_api/llm/` names a provider (grep test).

## Honest limits

- It's an **affinity index** from taste data, not a sales or wishlist forecast.
- New indie games are rarely in Qloo, so plans work through comparable games (16 of 20 recent indie titles resolved in Phase 0).
- **Accuracy scenarios:** 10 independent hypothetical games checked against Google Trends interest for a real shipped analogue (never used as a comp). The true #1 country was our #1 in **6 of 10** and in our top 3 in **8 of 10**; the original lift-only ranking managed 2 and 5. It misses where Qloo's data is thin (mobile MOBAs in Southeast Asia, Football Manager in Korea). Full table: [`docs/scenario-results.md`](docs/scenario-results.md). The earlier Steam-language backtest of the old ranking is in [`docs/backtest-results.md`](docs/backtest-results.md).
- City-level accuracy cannot be validated with free public data.
- Brands are global: Qloo's brand affinity ignores location.

## Repo map

```
apps/api      FastAPI: qloo/ (client, cache, trace), pipeline/ (S1-S8), llm/ (providers, prompts), grounding.py
apps/web      Next.js: app/ routes, components/ (SpawnMap, RegionScout, PlanView, LivePlan, TraceView, NewPlanForm, TileField, Sfx), lib/
packages/contracts   generated API types
docs/         product spec, verified Qloo contract, progress, decisions, backtest results
```

Progress against every acceptance criterion is tracked in [`docs/progress.md`](docs/progress.md); decisions in [`docs/10-risks-decisions.md`](docs/10-risks-decisions.md).
