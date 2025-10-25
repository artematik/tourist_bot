from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    BOT_TOKEN: str
    YANDEX_GEOCODER_API_KEY: Optional[str] = None

    # Настройки валидации
    MIN_INTERESTS_LENGTH: int = 3
    MAX_INTERESTS_LENGTH: int = 500
    MIN_TIME_HOURS: float = 0.5
    MAX_TIME_HOURS: float = 8
    
    class Config:
        env_file = ".env"

settings = Settings()