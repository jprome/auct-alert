"""
Configuration module for Auction Alerts.

Loads environment variables and provides configuration constants.
All sensitive values should be in .env file (never commit to git).
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class SupabaseConfig:
    """Supabase connection configuration."""
    url: str
    key: str  # Service role key for server-side operations
    
    @classmethod
    def from_env(cls) -> "SupabaseConfig":
        return cls(
            url=os.getenv("SUPABASE_URL", ""),
            key=os.getenv("SUPABASE_KEY", ""),
        )


@dataclass
class EmailConfig:
    """Email sending configuration (SMTP or SendGrid)."""
    provider: str  # "smtp" or "sendgrid"
    # SMTP settings
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    # SendGrid settings
    sendgrid_api_key: str
    # Common
    from_email: str
    from_name: str
    
    @classmethod
    def from_env(cls) -> "EmailConfig":
        return cls(
            provider=os.getenv("EMAIL_PROVIDER", "smtp"),
            smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_user=os.getenv("SMTP_USER", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            sendgrid_api_key=os.getenv("SENDGRID_API_KEY", ""),
            from_email=os.getenv("FROM_EMAIL", "alerts@auctionalerts.com"),
            from_name=os.getenv("FROM_NAME", "Auction Alerts"),
        )


@dataclass
class AppConfig:
    """Main application configuration."""
    # Miami coordinates (reference point for distance calculations)
    miami_lat: float = 25.7617
    miami_lng: float = -80.1918
    
    # Default intent parameters (can be adjusted by learning loop)
    default_max_price: float = 1200.0
    default_max_distance_miles: float = 100.0
    default_closing_hours: int = 48
    default_confidence_threshold: float = 0.6
    
    # Scraping settings
    request_timeout: int = 30
    request_delay: float = 2.0  # Seconds between requests (be nice to servers)
    
    # Alert tracking URL base (for click tracking)
    tracking_base_url: str = ""
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            miami_lat=float(os.getenv("MIAMI_LAT", "25.7617")),
            miami_lng=float(os.getenv("MIAMI_LNG", "-80.1918")),
            default_max_price=float(os.getenv("DEFAULT_MAX_PRICE", "1200.0")),
            default_max_distance_miles=float(os.getenv("DEFAULT_MAX_DISTANCE", "100.0")),
            default_closing_hours=int(os.getenv("DEFAULT_CLOSING_HOURS", "48")),
            default_confidence_threshold=float(os.getenv("DEFAULT_CONFIDENCE_THRESHOLD", "0.6")),
            tracking_base_url=os.getenv("TRACKING_BASE_URL", ""),
        )


# Global configuration instances (lazy loaded)
_supabase_config: Optional[SupabaseConfig] = None
_email_config: Optional[EmailConfig] = None
_app_config: Optional[AppConfig] = None


def get_supabase_config() -> SupabaseConfig:
    """Get Supabase configuration (cached)."""
    global _supabase_config
    if _supabase_config is None:
        _supabase_config = SupabaseConfig.from_env()
    return _supabase_config


def get_email_config() -> EmailConfig:
    """Get email configuration (cached)."""
    global _email_config
    if _email_config is None:
        _email_config = EmailConfig.from_env()
    return _email_config


def get_app_config() -> AppConfig:
    """Get app configuration (cached)."""
    global _app_config
    if _app_config is None:
        _app_config = AppConfig.from_env()
    return _app_config
