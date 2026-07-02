from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 本地默认值;docker 里通过环境变量覆盖(host = db)
    database_url: str = "postgresql+psycopg2://has:has@localhost:5432/has"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    # 逗号分隔的允许来源
    cors_origins: str = "http://localhost:3000"
    # 候选人邮件里的预约链接前缀
    frontend_base_url: str = "http://localhost:3000"
    # SMTP(Gmail:smtp.gmail.com:587 + App Password)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None  # 形如 "HAS Recruitment <me@gmail.com>"
    # 认证(magic link + session cookie)
    admin_email: str | None = None       # 启动时自动写入白名单的初始 admin
    magic_link_ttl_minutes: int = 15     # 登录链接有效期
    session_ttl_days: int = 7            # 会话有效期
    cookie_secure: bool = False          # 生产 HTTPS 环境置 true
    debug_expose_magic_link: bool = False  # 仅开发:request-link 响应直接带链接

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
