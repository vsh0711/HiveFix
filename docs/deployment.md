# Deploying HiveFix

The orchestrator is the only piece that needs a persistent host; the sandbox test
runs happen on GitHub Actions (triggered by the orchestrator), and the frontend can
stay local or deploy separately later.

## 1. Free-tier Redis and Qdrant

Render's own free tier doesn't include a managed Redis/Postgres add-on worth using
here, so these two are separate free-tier services:

- **Redis Cloud** (redis.io/try-free) → create a free 30MB database → copy its
  connection string into `REDIS_URL` (format: `redis://default:<password>@<host>:<port>`)
- **Qdrant Cloud** (cloud.qdrant.io) → create a free 1GB cluster → copy the cluster
  URL into `QDRANT_URL` and the API key into `QDRANT_API_KEY`

## 2. Generate an API key for the orchestrator

`POST /runs` (starting a new run) is gated behind `HIVEFIX_API_KEY` on any
non-empty value — required once the service is reachable from the internet, since
an unauthenticated write endpoint lets anyone who finds the URL spend your Groq and
GitHub quota and open PRs under your identity. Generate one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

`GET` endpoints (run status, the dashboard's read views) stay open regardless —
there's no login flow, and run data isn't sensitive for this project.

## 3. GitHub token for the orchestrator

The orchestrator needs its own `GITHUB_TOKEN` (separate from any local `gh` CLI
session) to: read issues, dispatch/poll the `sandbox-test.yml` workflow on the
HiveFix repo, and open PRs on target repos.

Create a **fine-grained personal access token** (github.com/settings/tokens) scoped to:
- `Actions: read and write` on the HiveFix repo (to dispatch/poll the sandbox workflow)
- `Contents: read and write` + `Pull requests: read and write` on whichever target
  repos you want HiveFix to open PRs against

Avoid a classic PAT with blanket `repo` scope across your whole account if you can
help it — scope it to just the repos HiveFix should touch.

## 4. Push HiveFix to GitHub

`HIVEFIX_REPO` must point at a real GitHub repo containing `.github/workflows/sandbox-test.yml`,
since that's what gets dispatched for every sandboxed test run.

## 5. Deploy the orchestrator on Render

1. In the Render dashboard: **New → Blueprint**, point it at the GitHub repo — it
   reads `render.yaml` at the repo root and creates the `hivefix-orchestrator` web
   service on the free plan automatically.
2. Render will prompt for the env vars marked `sync: false` in `render.yaml`
   (`GROQ_API_KEY`, `LANGCHAIN_API_KEY`, `GITHUB_TOKEN`, `HIVEFIX_REPO`,
   `HIVEFIX_API_KEY`, `REDIS_URL`, `QDRANT_URL`, `QDRANT_API_KEY`) — fill these in from steps 1–3.
3. First deploy builds `orchestrator/Dockerfile`. Render free-tier web services spin
   down after 15 minutes idle and cold-start on the next request — fine for a
   portfolio demo, worth knowing if a run seems to hang on the first request after
   a while.

## 6. Point the frontend at it

Set `NEXT_PUBLIC_ORCHESTRATOR_URL` to the Render service's public URL
(`https://hivefix-orchestrator.onrender.com`) wherever the frontend runs.
