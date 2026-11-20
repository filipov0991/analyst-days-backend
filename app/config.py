from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/app.db"
    app_env: str = "development"
    cookie_secure: bool = False
    allowed_origins: str = "http://localhost:3000"

    @property
    def origins(self) -> set[str]:
        return {item.strip() for item in self.allowed_origins.split(",") if item.strip()}

    @model_validator(mode="after")
    def validate_settings(self):
        if "*" in self.origins or "null" in self.origins:
            raise ValueError("ALLOWED_ORIGINS must contain explicit trusted origins")
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production")
        return self
