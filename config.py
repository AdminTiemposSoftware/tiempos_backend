from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "tiempos-backend"
    database_url: str
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    
    ticket_create: str | None = None
    ticket_by_schedule: str | None = None

    branch_by_banking: str | None = None
    branch_names: str | None = None
    branch_by_id: str | None = None
    branch_by_user: str | None = None
    branch_by_draw_schedule: str | None = None
    branch_create: str | None = None

    draw: str | None = None
    draw_by_branch: str | None = None
    draw_by_banking: str | None = None
    draw_create: str | None = None
    draw_update: str | None = None
    draw_delete: str | None = None

    draw_schedule: str | None = None
    draw_schedule_names: str | None = None
    draw_schedule_create: str | None = None
    draw_schedule_update: str | None = None
    draw_schedule_branch_create: str | None = None

    draw_day: str | None = None
    draw_day_create: str | None = None
    draw_day_update: str | None = None
    draw_day_delete: str | None = None
    
    banking_by_user: str | None = None
    banking_create: str | None = None

    user: str | None = None
    user_create: str | None = None

    prohibited_create: str | None = None
    prohibited_update: str | None = None
    prohibited_delete: str | None = None
    prohibited_by_banking_id: str | None = None
    prohibited_by_branch_id: str | None = None

    report_today: str | None = None
    report_filtered: str | None = None

    winner_by_banking_id: str | None = None
    winner_create: str | None = None
    
    number_by_draw_schedule: str | None = None

    auth_user: str | None = None
    auth_secret: str = ""
    auth_token_ttl_seconds: int = 86400

    auth_cookie_name_puesto: str = "session_puesto"
    auth_cookie_name_banca: str = "session_banca"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
