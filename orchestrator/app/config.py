import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
    groq_model: str = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
    # Groq's free tier reserves rate-limit budget based on the REQUESTED max_tokens
    # ceiling, not actual usage — leaving it unset defaults to the model's own max
    # (well over 1000), so even a single call can be rejected by the 1000
    # output-tokens-per-minute cap before generating a single token. Capped safely
    # under that limit; no retry/backoff can work around an unbounded request.
    groq_max_tokens: int = int(os.environ.get("GROQ_MAX_TOKENS", "800"))

    github_token: str = os.environ.get("GITHUB_TOKEN", "")
    hivefix_repo: str = os.environ.get("HIVEFIX_REPO", "")

    # Shared secret required on write endpoints (starting a run) — an unauthenticated
    # POST /runs lets anyone who finds the URL spend the deployed owner's Groq/GitHub
    # quota and open PRs under their identity. Left empty, auth is skipped (local
    # dev convenience); any deployment reachable from the internet MUST set this.
    hivefix_api_key: str = os.environ.get("HIVEFIX_API_KEY", "")

    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    qdrant_url: str = os.environ.get("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: str = os.environ.get("QDRANT_API_KEY", "")
    qdrant_collection: str = os.environ.get("QDRANT_COLLECTION", "hivefix_code_chunks")

    max_patch_attempts: int = int(os.environ.get("MAX_PATCH_ATTEMPTS", "3"))
    sandbox_poll_interval_seconds: int = int(os.environ.get("SANDBOX_POLL_INTERVAL_SECONDS", "10"))
    sandbox_poll_timeout_seconds: int = int(os.environ.get("SANDBOX_POLL_TIMEOUT_SECONDS", "900"))


settings = Settings()
