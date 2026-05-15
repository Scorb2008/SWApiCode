from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    bot_token: str = ""
    admin_ids: str = ""

    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""

    database_url: str = "sqlite+aiosqlite:///data/bot.db"
    public_url: str = ""
    purchase_max_quantity: int = 10

    @property
    def admin_ids_list(self) -> list[int]:
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]


settings = Settings()
