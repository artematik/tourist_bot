# config.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    BOT_TOKEN: str
    IONET_API_KEY: str
    GEOAPIFY_API_KEY: Optional[str] = None
    YANDEX_GEOCODER_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"

settings = Settings()
