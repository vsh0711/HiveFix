import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
    groq_model: str = os.environ.get("GROQ_MODEL", "qwen/qwen3-32b")

    github_token: str = os.environ.get("GITHUB_TOKEN", "")
    hivefix_repo: str = os.environ.get("HIVEFIX_REPO", "")

    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    qdrant_url: str = os.environ.get("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: str = os.environ.get("QDRANT_API_KEY", "")
    qdrant_collection: str = os.environ.get("QDRANT_COLLECTION", "hivefix_code_chunks")

    max_patch_attempts: int = int(os.environ.get("MAX_PATCH_ATTEMPTS", "2"))
    sandbox_poll_interval_seconds: int = int(os.environ.get("SANDBOX_POLL_INTERVAL_SECONDS", "10"))
    sandbox_poll_timeout_seconds: int = int(os.environ.get("SANDBOX_POLL_TIMEOUT_SECONDS", "900"))


settings = Settings()
