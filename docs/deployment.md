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

## 6. Deploy the frontend

`render.yaml` also defines `hivefix-frontend`, built from
`frontend/Dockerfile.prod` (a separate production image from the plain
`frontend/Dockerfile` local dev uses via docker-compose — that one runs `npm run
dev` for hot reload, not suitable for deployment). Syncing the blueprint after a
`render.yaml` change picks up new services automatically; if it doesn't, trigger it
manually from the Render dashboard.

Two real gotchas hit deploying this, both fixed in the current `Dockerfile.prod` —
worth knowing if you fork this or hit similar on another platform:

- **`COPY --from=builder /app/public ./public` failed on Render but worked
  locally.** `frontend/public/` only ever held an empty subdirectory; git doesn't
  track empty directories, so it existed on disk locally (where the build happened
  to pass) but was never actually committed — Render's fresh clone had no `public/`
  at all. Fixed with a tracked `.gitkeep`. If you add real static assets to
  `public/` later this stops being relevant, but it's a trap for any fresh Next.js
  scaffold with an unused `public/` folder.
- **Deployed cleanly, Render showed "Deployed," but every request 502'd.** Next's
  generated standalone `server.js` auto-binds to `process.env.PORT`. Render (like
  most platforms) injects its own `PORT` into every container's environment — if
  that doesn't match whatever port the platform's proxy actually forwards to
  (which for Docker-runtime services on Render appears to come from the
  Dockerfile's `EXPOSE`, not the injected `PORT`), the app ends up listening
  somewhere nothing ever connects to externally, while looking perfectly healthy
  to the platform itself. Fixed by pinning the port inline in the container's
  command (`CMD ["sh", "-c", "PORT=3000 node server.js"]`), which overrides
  whatever the platform injects for that process specifically — the same pattern
  the orchestrator's Dockerfile already used with a hardcoded `uvicorn --port 8000`.
