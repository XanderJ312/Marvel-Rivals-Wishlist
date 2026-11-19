from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # Sent in the User-Agent so wiki admins can reach us (MediaWiki API etiquette)
    wiki_contact: str = "not-set"

    data_dir: Path = ROOT / "data"

    wiki_base: str = "https://marvelrivals.fandom.com"
    request_delay: float = 1.0      # seconds between API requests
    image_delay: float = 0.3        # seconds between image downloads

    # Heroes are refreshed monthly on this day, skins daily
    heroes_day_of_month: int = 15
    scheduler_enabled: bool = True

    @property
    def api_url(self) -> str:
        return self.wiki_base + "/api.php"

    @property
    def user_agent(self) -> str:
        return f"RivalsSkinsMiniApp/1.0 (Telegram mini app; contact: {self.wiki_contact})"


settings = Settings()
