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
    support_contact: str = ""
    channel_url: str = ""
    privacy_policy_url: str = "https://telegra.ph/Politika-konfidencialnosti-04-01-26"
    user_agreement_url: str = "https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"

    @property
    def admin_ids_list(self) -> list[int]:
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    @property
    def yookassa_configured(self) -> bool:
        return bool(self.yookassa_shop_id and self.yookassa_secret_key)


settings = Settings()
