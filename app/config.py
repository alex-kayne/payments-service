from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")
    api_key: str = "secret-key"


settings = Settings()
