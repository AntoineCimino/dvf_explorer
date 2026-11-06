import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = os.getenv("DATABASE_URL", "postgresql://localhost:55432/dpe_db")
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"
    api_title: str = "DPE Search API"
    api_version: str = "0.1.0"

    class Config:
        env_file = ".env"


settings = Settings()
