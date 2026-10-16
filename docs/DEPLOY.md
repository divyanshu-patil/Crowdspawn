# Deploying a live demo

The hackathon asks for a live demo judges can use end to end. The API runs anywhere Docker runs; the web app runs on Vercel (or any Node host). Keys only ever live in the API host's environment.

## API (Render, from `render.yaml`)

1. Push the repo to GitHub (public, with `LICENSE`).
2. In Render: New → Blueprint → pick the repo. It reads `render.yaml` and builds `apps/api/Dockerfile`.
3. Fill the secrets Render asks for: `QLOO_API_KEY`, `OLLAMA_API_KEY`, and `CORS_ORIGINS` (the web URL from step 2 below, e.g. `https://crowdspawn.vercel.app`).
4. Check `https://<api-host>/health` shows `qloo: ok` and the LLM as configured.

Any Docker host works the same way: `docker build -t crowdspawn-api apps/api`, then run it with the same environment variables and `PORT`. SQLite lives in `/app/data`; on hosts without a disk it resets on redeploy, which only clears the cache and saved plans.

## Web (Vercel)

1. New Project → import the repo → Root Directory `apps/web` (Vercel detects Next.js and the pnpm workspace).
2. Environment variable `NEXT_PUBLIC_API_URL=https://<api-host>`.
3. Deploy, then put the Vercel URL into the API's `CORS_ORIGINS`.

## Before judging

- Warm the cache so demo inputs answer instantly: `cd apps/api && uv run python scripts/warm_demo.py https://<api-host>`.
- `/sample`, the scout map and the 50 popular places work without any Qloo calls (bundled snapshots).
- Per-IP limits (`PLANS_PER_IP_PER_HOUR`, `SCOUTS_PER_IP_PER_HOUR`) protect the 10,000-call monthly Qloo budget; the agent shares the plan limit.

Not verified here: the Docker image was written but not built (no Docker daemon on the build machine), and nothing has been deployed. Run the steps above and check `/health`.
