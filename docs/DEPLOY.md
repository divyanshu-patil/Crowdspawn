# Deploying a live demo

The hackathon asks for a live demo judges can use end to end. The API runs anywhere Docker runs; the web app runs on Vercel (or any Node host). Keys only ever live in the API host's environment.

## API (Render, from `render.yaml`)

1. Push the repo to GitHub (public, with `LICENSE`).
2. In Render: New → Blueprint → pick the repo. It reads `render.yaml` and builds `apps/api/Dockerfile`.
3. Fill the secrets Render asks for: `QLOO_API_KEY`, `OLLAMA_API_KEY`, and `CORS_ORIGINS` (the web URL from step 2 below, e.g. `https://crowdspawn.vercel.app`).
4. Check `https://<api-host>/health` shows `qloo: ok`, the LLM as configured, and `qloo_calls_left_today`.

`render.yaml` sets:

- `PLANS_PER_IP_PER_HOUR=6` (plans and agent runs share it) and `SCOUTS_PER_IP_PER_HOUR=120`.
- `QLOO_DAILY_CALL_CAP=400`: a global limit on live Qloo calls per UTC day, counted in SQLite. Cached answers never count. At the cap, new plans, agent runs and scout lookups fail closed with "Today's live Qloo budget is used up", while `/sample`, the scout map, the 50 popular places and anything already cached keep working. Unset, it defaults to 400 when `APP_ENV=production` and is off elsewhere; `0` turns it off.
- **A 1 GB persistent disk at `/app/data`.** It keeps the SQLite cache and saved plans across restarts, so judges get cached answers instead of ~100-call cold plans. **Disks need a paid Render instance.** On the free plan, delete the `disk:` block before creating the blueprint; the app still works, it just starts cold after every restart.

The Dockerfile runs uvicorn with `--proxy-headers --forwarded-allow-ips='*'`, so the per-IP limits see each visitor's address behind Render's proxy rather than the proxy's.

Any Docker host works the same way: `docker build -t crowdspawn-api apps/api`, then run it with the same environment variables and `PORT`. SQLite lives in `/app/data`; without a disk it resets on redeploy, which clears the cache and saved plans.

## Web (Vercel)

1. New Project → import the repo → Root Directory `apps/web` (Vercel detects Next.js and the pnpm workspace).
2. Environment variable `NEXT_PUBLIC_API_URL=https://<api-host>`.
3. Deploy, then put the Vercel URL into the API's `CORS_ORIGINS`.

## Before judging

- Warm the cache so demo inputs answer instantly: `cd apps/api && uv run python scripts/warm_demo.py https://<api-host>`. It runs the scout map, the scout judge for the demo places, the sample and hero plans, and every example chip of the launch agent. Run it after each restart if there is no disk.
- A free or idle host can take 30–60 s to answer the first request. The web app then shows "Starting the server, this can take up to a minute…", and if the request fails, a retry button and a link to the sample plan.
- `/sample`, the scout map and the 50 popular places work without any Qloo calls (bundled snapshots).
- Per-IP limits (`PLANS_PER_IP_PER_HOUR`, `SCOUTS_PER_IP_PER_HOUR`) protect the 10,000-call monthly Qloo budget; the agent shares the plan limit.

Not verified here: the Docker image was written but not built (no Docker daemon on the build machine), and nothing has been deployed. Run the steps above and check `/health`.
