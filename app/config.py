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

    # Email Settings
    mail_username: str
    mail_password: str
    mail_from: str
    mail_port: int
    mail_server: str
    base_url: str = "https://netradrive.snehkr.in"
    
    # Mail API Key
    resend_api_key: str

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
