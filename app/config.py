import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Settings(BaseModel):
    base_dir: Path = Path(__file__).resolve().parents[1]
    user_data_dir: Path = base_dir / "user_data"

    llm_api_base: str = os.getenv("LLM_API_BASE", "http://localhost:8000/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "not-needed")
    llm_model: str = os.getenv("LLM_MODEL", "your-model-name")
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    llm_context_window: int = int(os.getenv("LLM_CONTEXT_WINDOW", "128000"))


settings = Settings()
