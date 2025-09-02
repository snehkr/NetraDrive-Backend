from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # MongoDB
    mongo_uri: str
    db_name: str

    # JWT
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int

    # Telegram
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_name: str
    telegram_workdir: str
    telegram_storage_chat_id: int

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
