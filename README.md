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
| S1 Resolve comps | `/entities` (plan) or `/search` (picker, LLM suggestions) | Real Qloo video game ids; unknown names are dropped, never invented |
| S2 Expand | `/v2/insights` `filter.type=urn:entity:videogame` + explainability | 20 similar games with the comps that drive each one |
| S3 Cities | `urn:heatmap` per city, for the comp set **and** a mainstream baseline (Minecraft, Fortnite, GTA V, Warzone) | Lift = mean `affinity_rank` of comp fans ÷ baseline, with confidence |
| S4 Audience | `urn:demographics` | Age and gender over/under-index |
| S5 Partners | `/v2/insights` for artist, podcast, movie, brand (+ `signal.location` for the top 3 cities) | Partners with affinity and Qloo's reasons |
| S6 Gap (optional) | `/v2/analysis/compare` | Tastes shared with your last game vs new ground |
| S7 Budget | none, deterministic | Split by lift × confidence, sums to exactly 100% |
| S8 Brief | none, LLM over S1–S7 facts | Prose that cites `[q12]` result ids; validated before display |

A typical plan with 5 comps and 12 cities uses 40 Qloo calls: 21.8 s on a cold cache, 2.2 s warm, 0 live calls on repeat.

### Why it can't exist without Qloo (the swap test)

Every city, entity, score and audience figure carries `source: "qloo"` and a `result_id` in the trace (tested: Q1). The LLM only suggests comp *names* (which Qloo must resolve) and words the brief. A grounding validator rejects any city, bold name, number or citation not present in the Qloo results, regenerates once, then falls back to a template (L7).

**Kill-switch test:** with `QLOO_API_KEY` empty or wrong, a plan ends `failed` with `qloo_unconfigured` / `qloo_auth`, no cities or brief are produced, and no LLM call is made (`tests/test_api.py::test_kill_switch_*`, and the error screen in the UI).

**LLM-swap test:** switching `LLM_PROVIDER` between `ollama_cloud`, `gemini`, `openai_compat` and `fake` changes only the brief; the rest of the plan JSON is identical (`test_provider_swap_changes_only_brief`). Only `apps/api/src/crowdspawn_api/llm/` names a provider (grep test).

## Honest limits

- It's an **affinity index** from taste data, not a sales or wishlist forecast.
- New indie games are rarely in Qloo, so plans work through comparable games (16 of 20 recent indie titles resolved in Phase 0).
- **Backtest:** against Steam review languages for 6 shipped games, the lift ranking beat a popularity baseline in **1 of 6** (mean Spearman −0.21 vs 0.40). Lift is inflated where mainstream gamers are scarce in Qloo's data (Tokyo, Seoul). Read it as a taste-informed starting hypothesis, and test with small campaigns. Full table: [`docs/backtest-results.md`](docs/backtest-results.md).
- City-level accuracy cannot be validated with free public data.
- Brands are global: Qloo's brand affinity ignores location.

## Repo map

```
apps/api      FastAPI: qloo/ (client, cache, trace), pipeline/ (S1-S8), llm/ (providers, prompts), grounding.py
apps/web      Next.js: app/ routes, components/ (SpawnMap, PlanView, LivePlan, TraceView, NewPlanForm), lib/
packages/contracts   generated API types
docs/         product spec, verified Qloo contract, progress, decisions, backtest results
```

Progress against every acceptance criterion is tracked in [`docs/progress.md`](docs/progress.md); decisions in [`docs/10-risks-decisions.md`](docs/10-risks-decisions.md).
