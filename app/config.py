from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    rabbitmq_url: str
    api_key: str = "super-secret-key"
    outbox_poll_interval: float = 1.0
    outbox_batch_size: int = 20

    model_config = SettingsConfigDict(extra="ignore", env_file=".env")


settings = Settings()
