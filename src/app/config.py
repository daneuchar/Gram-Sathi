from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # AWS Bedrock
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "ap-south-1"
    bedrock_model_id: str = "global.amazon.nova-2-lite-v1:0"

    # Sarvam AI
    sarvam_api_key: str = ""

    # Exotel
    exotel_api_key: str = ""
    exotel_api_token: str = ""
    exotel_account_sid: str = ""
    exotel_phone_number: str = ""

    # External APIs
    data_gov_api_key: str = ""
    indian_api_key: str = ""

    # Amazon Q Business
    amazon_q_app_id: str = ""
    amazon_q_index_id: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://gramvaani:gramvaani@localhost:5432/gramvaani"

    # App
    debug: bool = False

    model_config = {"env_file": ".env"}


settings = Settings()
