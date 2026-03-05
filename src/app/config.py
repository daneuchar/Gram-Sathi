from pathlib import Path
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    # AWS Bedrock
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"
    bedrock_model_id: str = "us.amazon.nova-lite-v1:0"

    # LLM — set llm_provider="openai" to use OpenAI instead of Bedrock
    llm_provider: str = "bedrock"  # "bedrock" | "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""

    # Sarvam AI
    sarvam_api_key: str = ""

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # External APIs
    data_gov_api_key: str = ""
    indian_api_key: str = ""

    # Amazon Q Business
    amazon_q_app_id: str = ""
    amazon_q_index_id: str = ""

    # LiveKit
    livekit_url: str = ""           # e.g. wss://my-app.livekit.cloud
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # LLM model on Bedrock
    llama_model_id: str = "us.meta.llama3-3-70b-instruct-v1:0"

    # Database
    database_url: str = "postgresql+asyncpg://gramvaani:gramvaani@localhost:5432/gramvaani"

    # App
    debug: bool = False
    public_url: str = ""  # e.g. https://xxxx.ngrok-free.dev

    model_config = {"env_file": str(_ENV_FILE), "extra": "ignore"}


settings = Settings()
