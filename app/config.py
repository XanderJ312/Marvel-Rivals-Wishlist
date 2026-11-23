from pathlib import Path

from pydantic import Field
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
    heroes_day_of_month: int = Field(15, ge=1, le=28)  # <= 28 so the day exists in every month
    scheduler_enabled: bool = True

    # Telegram (optional, without a token the app works in the browser only)
    telegram_bot_token: str = ""
    public_url: str = ""            # permanent HTTPS URL, empty = use the Cloudflare quick tunnel
    tunnel_metrics_url: str = ""    # set in docker-compose.yml
    menu_button_text: str = "Skins"
    telegram_api_base: str = "https://api.telegram.org"

    @property
    def api_url(self) -> str:
        return self.wiki_base + "/api.php"

    @property
    def user_agent(self) -> str:
        return f"RivalsSkinsMiniApp/1.0 (Telegram mini app; contact: {self.wiki_contact})"


settings = Settings()
