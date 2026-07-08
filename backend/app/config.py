from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Local defaults; overridden by env vars inside docker (host = db)
    database_url: str = "postgresql+psycopg2://has:has@localhost:5432/has"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    # Comma-separated allowed origins
    cors_origins: str = "http://localhost:3000"
    # Base URL used for booking links in candidate emails
    frontend_base_url: str = "http://localhost:3000"
    # SMTP (Gmail: smtp.gmail.com:587 + App Password)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None  # e.g. "HAS Recruitment <me@gmail.com>"
    # Authentication (Email OTP + session cookie)
    admin_email: str | None = None       # initial admin seeded into the allowlist at startup
    otp_ttl_minutes: int = 10            # OTP validity (5-10 minutes)
    otp_max_attempts: int = 5            # max failed attempts per code
    session_ttl_days: int = 7            # session lifetime
    cookie_secure: bool = False          # set true in HTTPS production
    debug_expose_otp: bool = False       # dev only: echo the code in the request-otp response
    # Object storage (resume files)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "has"
    minio_secret_key: str = "hasminio123"
    minio_bucket: str = "resumes"
    minio_secure: bool = False

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
