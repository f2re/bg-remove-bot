from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str
    ADMIN_IDS: str

    # Database - can use either DATABASE_URL or individual DB_* variables
    DATABASE_URL: Optional[str] = None
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "bg_removal_bot"
    DB_USER: str = "bgremove_user"
    DB_PASSWORD: str = ""

    # OpenRouter
    OPENROUTER_API_KEY: str
    # Use Gemini 2.5 Flash Image for image editing/generation
    # This model supports both image input and image output with modalities
    OPENROUTER_MODEL: str = "google/gemini-2.5-flash-image-preview"

    # YooKassa (ЮКасса)
    YOOKASSA_SHOP_ID: str
    YOOKASSA_SECRET_KEY: str
    YOOKASSA_RETURN_URL: str = "https://t.me/your_bot"  # URL to return after payment

    # Pricing (in kopecks)
    PACKAGE_1_PRICE: int = 5000
    PACKAGE_5_PRICE: int = 20000
    PACKAGE_10_PRICE: int = 35000
    PACKAGE_50_PRICE: int = 150000

    # Free images for new users
    FREE_IMAGES_COUNT: int = 3

    # Logging
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def database_url(self) -> str:
        """Get async database URL for PostgreSQL"""
        # If DATABASE_URL is set, use it directly
        if self.DATABASE_URL:
            return self.DATABASE_URL
        # Otherwise, construct from individual components
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def admin_ids_list(self) -> List[int]:
        """Get list of admin telegram IDs"""
        return [int(id.strip()) for id in self.ADMIN_IDS.split(",") if id.strip()]


# Global settings instance
settings = Settings()
