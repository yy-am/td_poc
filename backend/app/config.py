"""应用配置 — 从 .env 文件读取"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "tda_tdp_runtime.db"


class Settings(BaseSettings):
    # 数据库
    DATABASE_URL: str = f"sqlite+aiosqlite:///./{DEFAULT_SQLITE_PATH.name}"

    # LLM
    LLM_BASE_URL: str = "https://jeniya.cn/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "deepseek-v3.2"
    LLM_TEMPERATURE: float = 0.1

    # Embeddings
    EMBEDDING_BASE_URL: str = "https://jeniya.cn/v1"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    # App
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
    )

    @property
    def database_dialect(self) -> str:
        return make_url(self.DATABASE_URL).get_backend_name()

    @property
    def is_sqlite(self) -> bool:
        return self.database_dialect == "sqlite"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
