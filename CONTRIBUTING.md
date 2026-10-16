# Contributing to Crowdspawn

Thanks for helping. This guide covers setup, the commands you need, and the few rules that keep Crowdspawn honest.

## Setup

### Requirements

- Node 24 or newer
- pnpm 11 (`corepack enable` picks the version pinned in `package.json`)
- [uv](https://docs.astral.sh/uv/). It fetches Python 3.12 for the API, so you don't need to install Python yourself.

### Install

```sh
git clone https://github.com/divyanshu-patil/Crowdspawn.git
cd Crowdspawn
pnpm install                      # installs the web app and runs `uv sync` for the API
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
```

### Keys

Put keys in `apps/api/.env` only. That file is git-ignored.

| Variable | Needed for | Without it |
|---|---|---|
| `QLOO_API_KEY` | All live data | Plans, the scout and the agent fail closed with `qloo_unconfigured`. `/sample` and the 50 bundled scout places still work. |
| `OLLAMA_API_KEY` (default `LLM_PROVIDER=ollama_cloud`) | Brief prose, comp and culture suggestions, the agent, judge explanations | The brief falls back to a grounded template. Suggestions and the agent are unavailable. |
| `GEMINI_API_KEY` / `OPENAI_COMPAT_*` | Optional: switch `LLM_PROVIDER` to `gemini` or `openai_compat` | Not needed |

`apps/web/.env.local` holds only `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). Never put a key there, because anything starting with `NEXT_PUBLIC_` is sent to the browser.

### Run

```sh
pnpm dev        # web on http://localhost:3000, API on http://localhost:8000 (hot reload)
```

To run one side only, use `pnpm --filter web dev` or `pnpm --filter api dev`. The API's OpenAPI docs are at http://localhost:8000/docs.

## Commands

| Command | What it does |
|---|---|
| `pnpm dev` | Web + API with hot reload |
| `pnpm lint` | ruff (check + format check) and ESLint |
| `pnpm check-types` | mypy --strict and tsc |
| `pnpm test` | API pytest on recorded fixtures (no network; coverage must stay at or above 80%) and web Vitest |
| `pnpm build` | Exports `apps/api/openapi.json` and builds the Next.js app |
| `pnpm contracts` | Regenerates the TypeScript types in `packages/contracts` from the API |
| `pnpm --filter api test:live` | Live smoke tests against real Qloo. Spends calls; never runs in CI |
| `pnpm format` | Prettier for TS and Markdown |

Before you open a PR, run what CI runs:

```sh
pnpm turbo run lint check-types test build
```

CI (`.github/workflows/ci.yml`) runs exactly this with `APP_ENV=test` and no secrets.

## Repo layout

```
apps/api      FastAPI service (Python 3.12, uv)
  src/crowdspawn_api/qloo/       Qloo client: rate limit, retries, SQLite cache, call trace
  src/crowdspawn_api/pipeline/   plan steps S1-S8, agent, scout, judge
  src/crowdspawn_api/llm/        LLM providers and prompts (the only place a provider is named)
  tests/                         pytest; tests/fixtures holds recorded Qloo responses
  scripts/                       fixtures, snapshots, accuracy scenarios, demo warm-up
apps/web      Next.js 16 app: app/ routes, components/, lib/
packages/contracts   TypeScript types generated from the API
docs/         how it works, verified Qloo contract, accuracy results, deploy guide
```

Start with [`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md), then [`docs/qloo-contract.md`](docs/qloo-contract.md). For UI work, match the existing look: the sketchpad grid, ink borders with a solid offset side, marker yellow and ember orange, no blurred shadows.

> Next.js 16 and Turborepo 2.11 differ from older versions. Check the docs bundled in `node_modules/next/dist/docs/` and the `turbo` package before changing config.

## Ground rules

These rules aren't optional. Tests enforce several of them.

1. **Qloo is the only source of data.** The LLM writes prose and proposes names that Qloo must resolve. It never supplies cities, entities, scores or statistics. Any new LLM output that contains facts needs a grounding check (see `grounding.py` and `pipeline/agent.py`).
2. **Fail closed.** If Qloo fails, the feature fails with a clear error. Never fall back to mock or LLM data outside `APP_ENV=test`.
3. **Verify before you code.** Don't guess Qloo parameter names. Make the call live, record it with `scripts/record_fixture.py`, and note what you learn in [`docs/qloo-contract.md`](docs/qloo-contract.md).
4. **Provider-agnostic LLM.** Only files under `apps/api/src/crowdspawn_api/llm/` may name a provider. Everything else uses the `LLMProvider` protocol. A grep test checks this.
5. **Secrets.** Keys live only in git-ignored `.env` files. Never log, trace, return or commit them, and never send them to the browser.
6. **Respect the Qloo budget:** 5 requests per second and 10,000 calls per month. Cache results, cap calls per run, and use fixtures in tests. Mark any test that hits a real API with `@pytest.mark.live`.
7. **Honest labels.** Call results an affinity index or taste match, not a sales forecast or player count. Show limits in the UI.

## Tests

- **API:** tests replay recorded Qloo responses from `apps/api/tests/fixtures`, so they need no network. To record a new fixture:

  ```sh
  cd apps/api
  uv run python scripts/record_fixture.py /search search/hades query=Hades types=urn:entity:videogame
  ```

  The key is read from `.env` and never written to the fixture.
- **Sample plan:** `uv run python scripts/export_plan_fixtures.py <plan_id> <fixture_dir> --sample` exports a finished plan as fixtures and as the `/sample` data, with no live calls.
- **Scout snapshot:** `uv run python scripts/snapshot_scout.py` refreshes the 50 bundled places. It's live and costs about 19 calls per uncached place.
- **Web:** Vitest, in `apps/web/tests`.
- **Changing an API schema:** run `pnpm contracts` and commit the regenerated types with the change.

## Commits and pull requests

- Keep commits small and use conventional prefixes with a scope, e.g. `feat(scout): …`, `fix(web): …`, `test(api): …`, `docs: …`.
- One topic per PR. Say what changed, why, and how you verified it. For UI changes, include a screenshot and check the page at 360 px width and with the keyboard.
- If a doc in `docs/` disagrees with live behaviour, trust the live behaviour and update the doc in the same PR.
- Open an issue to discuss a new feature before building it.

## Licence

Crowdspawn is MIT licensed. By contributing you agree that your contributions are licensed under the same terms.
