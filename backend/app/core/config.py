from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # 공공데이터포털 서비스키
    fsc_api_key: str = ""

    # Redash (Trino 쿼리 프록시)
    redash_url: str = "https://redash.quantit.io"
    redash_api_key: str = ""

    # ngrok / 배포
    ngrok_authtoken: str = ""
    ngrok_domain: str = ""
    allowed_origins: str = ""

    # OpenDART (금융감독원 전자공시)
    dart_api_key: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
