"""
Base scraper class for auction sources.

All scrapers inherit from BaseScraper and implement:
- fetch_listings(): Get raw data from the source
- parse_listing(): Extract item data from raw HTML/JSON
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional
import requests
from datetime import datetime

from ..config import get_app_config
from ..db import get_db
from ..models import AuctionSource

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """
    Abstract base class for auction scrapers.
    
    Provides common functionality:
    - HTTP requests with rate limiting
    - Error handling and retries
    - Raw data storage
    
    Subclasses must implement:
    - source: The AuctionSource enum value
    - fetch_listings(): Get listings from the source
    - parse_listing(): Parse raw data into item dict
    """
    
    source: AuctionSource  # Subclass must set this
    
    def __init__(self):
        """Initialize the scraper."""
        self.config = get_app_config()
        self.db = get_db()
        self.session = requests.Session()
        
        # Set a reasonable user agent
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AuctionAlerts/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        
        self._last_request_time: float = 0
    
    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.config.request_delay:
            time.sleep(self.config.request_delay - elapsed)
        self._last_request_time = time.time()
    
    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """
        Make a GET request with rate limiting and error handling.
        
        Args:
            url: The URL to fetch
            **kwargs: Additional arguments to pass to requests.get()
            
        Returns:
            Response object or None if request failed
        """
        self._rate_limit()
        
        try:
            kwargs.setdefault("timeout", self.config.request_timeout)
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return None
    
    def _store_raw(self, url: str, content: str, content_type: str = "html") -> str:
        """
        Store raw content in Supabase.
        
        Args:
            url: The source URL
            content: Raw HTML or JSON string
            content_type: "html" or "json"
            
        Returns:
            The raw_data ID
        """
        return self.db.store_raw_data(
            source=self.source,
            url=url,
            content=content,
            content_type=content_type,
        )
    
    @abstractmethod
    def fetch_listings(self, **kwargs) -> list[dict]:
        """
        Fetch listings from the source.
        
        Returns:
            List of raw item dictionaries (not yet normalized)
        """
        pass
    
    @abstractmethod
    def parse_listing(self, raw_data: str, url: str) -> list[dict]:
        """
        Parse raw HTML/JSON into item dictionaries.
        
        Args:
            raw_data: The raw HTML or JSON string
            url: The source URL (for reference)
            
        Returns:
            List of item dictionaries with extracted fields
        """
        pass
    
    def scrape(self, **kwargs) -> list[dict]:
        """
        Main entry point: fetch and parse listings.
        
        This method:
        1. Fetches raw data from the source
        2. Stores raw data in Supabase
        3. Parses and returns item dictionaries
        
        Returns:
            List of item dictionaries ready for normalization
        """
        logger.info(f"Starting scrape for {self.source.value}")
        
        try:
            items = self.fetch_listings(**kwargs)
            logger.info(f"Scraped {len(items)} items from {self.source.value}")
            return items
        except Exception as e:
            logger.error(f"Scrape failed for {self.source.value}: {e}")
            return []
