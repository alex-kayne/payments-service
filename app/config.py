from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    rabbitmq_url: str
    api_key: str = "super-secret-key"
    outbox_poll_interval: float = 1.0
    outbox_batch_size: int = 20
    process_min_seconds: float = 2.0
    process_max_seconds: float = 5.0
    failure_rate: float = 0.1

    model_config = SettingsConfigDict(extra="ignore", env_file=".env")


settings = Settings()
