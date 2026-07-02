from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 本地默认值;docker 里通过环境变量覆盖(host = db)
    database_url: str = "postgresql+psycopg2://has:has@localhost:5432/has"
    anthropic_api_key: str | None = None
    # 逗号分隔的允许来源
    cors_origins: str = "http://localhost:3000"
    # 候选人邮件里的预约链接前缀
    frontend_base_url: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
