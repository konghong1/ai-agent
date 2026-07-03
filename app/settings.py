from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    langsmith_project: str = Field(default="local-langchain-agent", alias="LANGSMITH_PROJECT")
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    database_url: str = Field(default=f"sqlite:///{ROOT_DIR / 'agent.db'}", alias="DATABASE_URL")
    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=60 * 24 * 7, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    # ── Vector Store Configuration ──────────────────────────────────
    # Supported backends: "chroma", "faiss", "milvus"
    vector_store_backend: str = Field(default="chroma", alias="VECTOR_STORE_BACKEND")
    vector_store_path: str = Field(default=str(ROOT_DIR / "vector_db"), alias="VECTOR_STORE_PATH")
    # Milvus-specific (only used when backend="milvus")
    milvus_host: str = Field(default="localhost", alias="MILVUS_HOST")
    milvus_port: int = Field(default=19530, alias="MILVUS_PORT")
    milvus_collection_prefix: str = Field(default="kb_", alias="MILVUS_COLLECTION_PREFIX")


@lru_cache
def get_settings() -> Settings:
    return Settings()
