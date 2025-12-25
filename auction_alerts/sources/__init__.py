"""
Sources package - Scrapers for auction data sources.

Each scraper module handles:
1. Fetching raw HTML/JSON from the source
2. Storing raw data in Supabase
3. Extracting item data for normalization
"""

from .base import BaseScraper
from .estatesales import EstateSalesScraper
from .hibid import HiBidScraper
from .florida_surplus import FloridaSurplusScraper

__all__ = [
    "BaseScraper",
    "EstateSalesScraper", 
    "HiBidScraper",
    "FloridaSurplusScraper",
]
