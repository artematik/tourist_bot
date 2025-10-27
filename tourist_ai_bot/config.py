from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    BOT_TOKEN: str
    YANDEX_GEOCODER_API_KEY: Optional[str] = None
    IONET_API_KEY: str

    class Config:
        env_file = ".env"

settings = Settings()
