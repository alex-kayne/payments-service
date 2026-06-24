from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")


settings = Settings()
