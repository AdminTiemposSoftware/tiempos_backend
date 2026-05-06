from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "tiempos-backend"
    database_url: str
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    sales: str | None = None
    tickets: str | None = None
    branch: str | None = None
    branch_create: str | None = None
    branch_update: str | None = None
    branch_delete: str | None = None
    draw: str | None = None
    draw_create: str | None = None
    draw_update: str | None = None
    draw_delete: str | None = None
    draw_schedule: str | None = None
    draw_schedule_create: str | None = None
    draw_schedule_update: str | None = None
    draw_schedule_delete: str | None = None
    draw_day: str | None = None
    draw_day_create: str | None = None
    draw_day_update: str | None = None
    draw_day_delete: str | None = None
    banking: str | None = None
    banking_create: str | None = None
    banking_update: str | None = None
    banking_delete: str | None = None
    user: str | None = None
    user_create: str | None = None
    user_update: str | None = None
    user_delete: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
