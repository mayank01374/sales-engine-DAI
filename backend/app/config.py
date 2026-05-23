from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    database_url: str = Field(default="sqlite:///./decoverai_signal.db", alias="DATABASE_URL")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")
    firecrawl_api_key: str | None = Field(default=None, alias="FIRECRAWL_API_KEY")
    web_discovery_max_results: int = Field(default=60, alias="WEB_DISCOVERY_MAX_RESULTS")
    web_discovery_rate_limit_seconds: float = Field(default=2, alias="WEB_DISCOVERY_RATE_LIMIT_SECONDS")
    scraping_user_agent: str = Field(default="D-CoverAI-SignalBot/1.0", alias="SCRAPING_USER_AGENT")
    web_discovery_use_playwright: bool = Field(default=False, alias="WEB_DISCOVERY_USE_PLAYWRIGHT")
    enable_demo_data: bool = Field(default=False, alias="ENABLE_DEMO_DATA")
    enable_force_convert: bool = Field(default=False, alias="ENABLE_FORCE_CONVERT")
    daily_trigger_threshold: float = Field(default=70, alias="DAILY_TRIGGER_THRESHOLD")
    min_confidence_score: float = Field(default=60, alias="MIN_CONFIDENCE_SCORE")
    min_source_quality_score: float = Field(default=50, alias="MIN_SOURCE_QUALITY_SCORE")
    min_discovery_pain_score: float = Field(default=60, alias="MIN_DISCOVERY_PAIN_SCORE")
    min_dcover_fit_score: float = Field(default=60, alias="MIN_DCOVER_FIT_SCORE")
    min_sales_actionability_score: float = Field(default=60, alias="MIN_SALES_ACTIONABILITY_SCORE")
    max_signal_age_days: int = Field(default=90, alias="MAX_SIGNAL_AGE_DAYS")
    courtlistener_api_key: str | None = Field(default=None, alias="COURTLISTENER_API_KEY")
    max_per_source_domain: int = Field(default=4, alias="MAX_PER_SOURCE_DOMAIN")
    max_per_trigger_category: int = Field(default=5, alias="MAX_PER_TRIGGER_CATEGORY")
    max_per_same_party: int = Field(default=2, alias="MAX_PER_SAME_PARTY")
    source_allowlist: str = Field(default="", alias="SOURCE_ALLOWLIST")
    source_blocklist: str = Field(default="", alias="SOURCE_BLOCKLIST")
    discovery_query_settings: str = Field(default="{}", alias="DISCOVERY_QUERY_SETTINGS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def origins(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(',') if x.strip()]

    class Config:
        env_file = ".env"
        populate_by_name = True

settings = Settings()
