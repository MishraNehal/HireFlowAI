import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "HireFlow AI"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./hireflow.db")
    
    # Nexus API settings
    NEXUS_API_BASE: str = os.getenv("NEXUS_API_BASE", "https://apidev.navigatelabsai.com")
    NEXUS_API_KEY: str = os.getenv("NEXUS_API_KEY", "mock-nexus-key-1234")
    
    # RAG Settings
    CHROMA_PERSIST_DIRECTORY: str = os.getenv("CHROMA_PERSIST_DIRECTORY", "./chroma_db")
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

    class Config:
        case_sensitive = True

settings = Settings()
