"""Application configuration using Pydantic Settings.

Design Decisions:
    - All configuration is loaded from environment variables (12-Factor App).
    - Pydantic validates types at startup — misconfigurations fail fast.
    - Hierarchical grouping keeps related settings together.
    - Defaults are set for local development; production overrides via .env or env vars.
    - The Settings class is a singleton via lru_cache to avoid re-reading env on every call.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Uses Pydantic Settings v2 for type-safe, validated configuration.
    Environment variables override defaults. A `.env` file in the project root
    is loaded automatically if present.
    """

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = Field(default="Ardee-RAG-ChatBot", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    app_env: str = Field(
        default="development", description="Environment: development | staging | production"
    )
    app_debug: bool = Field(default=True, description="Enable debug mode")
    app_host: str = Field(default="0.0.0.0", description="Server bind host")
    app_port: int = Field(default=8000, description="Server bind port")
    app_log_level: str = Field(default="DEBUG", description="Log level")

    # ── Database ─────────────────────────────────────────────────────────────
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_db: str = Field(default="ardee_rag", description="PostgreSQL database name")
    postgres_user: str = Field(default="ardee", description="PostgreSQL user")
    postgres_password: str = Field(
        default="changeme_in_production", description="PostgreSQL password"
    )

    @property
    def database_url(self) -> str:
        """Build async database URL for SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Redis ────────────────────────────────────────────────────────────────
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: str = Field(default="", description="Redis password")
    redis_db: int = Field(default=0, description="Redis database index")

    @property
    def redis_url(self) -> str:
        """Build Redis connection URL."""
        if self.redis_password:
            return (
                f"redis://:{self.redis_password}"
                f"@{self.redis_host}:{self.redis_port}/{self.redis_db}"
            )
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ── OpenAI ───────────────────────────────────────────────────────────────
    openai_api_key: str = Field(default="sk-placeholder", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o", description="OpenAI chat model")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", description="OpenAI embedding model"
    )
    openai_embedding_dimensions: int = Field(
        default=1536, description="Embedding vector dimensions"
    )

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret_key: str = Field(
        default="change-this-to-a-random-64-char-string-in-production",
        description="JWT signing secret",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_access_token_expire_minutes: int = Field(
        default=30, description="Access token TTL in minutes"
    )
    jwt_refresh_token_expire_days: int = Field(default=7, description="Refresh token TTL in days")

    # ── Rate Limiting ────────────────────────────────────────────────────────
    rate_limit_per_minute: int = Field(default=60, description="Max requests per minute per user")

    # ── File Upload ──────────────────────────────────────────────────────────
    max_upload_size_mb: int = Field(default=50, description="Max file upload size in MB")
    allowed_extensions: str = Field(
        default=".pdf", description="Comma-separated allowed extensions"
    )
    upload_dir: str = Field(
        default="backend/storage/uploads/rag",
        description="Local directory for uploaded RAG PDFs",
    )

    @property
    def allowed_extensions_list(self) -> list[str]:
        """Parse allowed upload extensions into lowercase values."""
        return [
            extension.strip().lower()
            for extension in self.allowed_extensions.split(",")
            if extension.strip()
        ]

    @property
    def max_upload_size_bytes(self) -> int:
        """Return max upload size in bytes."""
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def upload_dir_path(self) -> Path:
        """Resolve upload directory relative to the backend root when needed."""
        upload_path = Path(self.upload_dir)
        if upload_path.is_absolute():
            return upload_path
        return Path(__file__).resolve().parents[2] / upload_path

    # ── Semantic Cache ───────────────────────────────────────────────────────
    semantic_cache_threshold: float = Field(
        default=0.95, description="Cosine similarity threshold for cache hit"
    )
    semantic_cache_ttl_seconds: int = Field(default=3600, description="Cache entry TTL in seconds")

    # ── RAG ───────────────────────────────────────────────────────────────────
    rag_chunk_size: int = Field(default=512, description="Text chunk size in tokens")
    rag_chunk_overlap: int = Field(default=50, description="Overlap between chunks")
    rag_top_k: int = Field(default=5, description="Number of retrieved chunks")
    rag_embedding_batch_size: int = Field(default=100, description="Embedding batch size")
    rag_min_vector_score: float = Field(
        default=0.25,
        description="Minimum vector similarity required before calling the LLM",
    )
    chat_history_messages_limit: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Number of previous chat messages to include in answers",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        description="Comma-separated allowed CORS origins",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins string into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings (singleton pattern).

    Uses lru_cache to ensure Settings is instantiated only once,
    reading environment variables a single time at startup.
    """
    return Settings()
