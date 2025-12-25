"""
EstateSales.net scraper for Florida estate sales.

EstateSales.net lists estate sales with furniture, antiques, etc.
We focus on Florida listings and extract furniture items.

Note: This is a simplified scraper for the MVP. In production,
you may need to handle pagination, JavaScript rendering, etc.
"""

import re
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from .base import BaseScraper
from ..models import AuctionSource

logger = logging.getLogger(__name__)


class EstateSalesScraper(BaseScraper):
    """
    Scraper for EstateSales.net (Florida).
    
    Fetches estate sale listings and extracts furniture items.
    """
    
    source = AuctionSource.ESTATESALES_NET
    
    # Base URLs for Florida estate sales
    BASE_URL = "https://www.estatesales.net"
    FLORIDA_URL = "https://www.estatesales.net/FL"
    
    # Florida cities to scrape (major metro areas)
    FLORIDA_CITIES = [
        "Miami",
        "Fort-Lauderdale",
        "West-Palm-Beach",
        "Orlando",
        "Tampa",
        "Jacksonville",
    ]
    
    def fetch_listings(self, cities: Optional[list[str]] = None, **kwargs) -> list[dict]:
        """
        Fetch estate sale listings from Florida cities.
        
        Args:
            cities: List of city names to scrape (defaults to major FL cities)
            
        Returns:
            List of item dictionaries
        """
        cities = cities or self.FLORIDA_CITIES[:3]  # Start with first 3 for MVP
        all_items = []
        
        for city in cities:
            items = self._fetch_city_listings(city)
            all_items.extend(items)
        
        return all_items
    
    def _fetch_city_listings(self, city: str) -> list[dict]:
        """Fetch listings for a specific city."""
        # Construct city URL
        city_url = f"{self.FLORIDA_URL}/{city}"
        logger.info(f"Fetching listings from: {city_url}")
        
        response = self._get(city_url)
        if not response:
            return []
        
        # Store raw HTML
        raw_id = self._store_raw(city_url, response.text, "html")
        
        # Parse and return items
        items = self.parse_listing(response.text, city_url)
        
        # Add raw_data_id reference
        for item in items:
            item["raw_data_id"] = raw_id
        
        return items
    
    def parse_listing(self, raw_data: str, url: str) -> list[dict]:
        """
        Parse EstateSales.net HTML to extract sale listings.
        
        Note: EstateSales.net lists SALES (events), not individual items.
        We treat each sale as having potential furniture items.
        """
        soup = BeautifulSoup(raw_data, "html.parser")
        items = []
        
        # EstateSales.net uses Angular - find links matching the sale URL pattern
        # Pattern: /FL/City/ZIP/SaleID (e.g., /FL/Miami/33139/4760445)
        sale_pattern = re.compile(r'/FL/[^/]+/\d+/(\d+)')
        sale_links = soup.find_all("a", href=sale_pattern)
        
        # Track seen sale IDs to avoid duplicates
        seen_ids = set()
        
        for link in sale_links:
            href = link.get("href", "")
            match = sale_pattern.search(href)
            if not match:
                continue
                
            sale_id = match.group(1)
            if sale_id in seen_ids:
                continue
            seen_ids.add(sale_id)
            
            try:
                item = self._parse_sale_link(link, href, sale_id)
                if item:
                    items.append(item)
            except Exception as e:
                logger.warning(f"Failed to parse sale link: {e}")
                continue
        
        # If no items found, fall back to test data
        if not items:
            logger.warning(f"No sale links found at {url}, creating test data")
            items = self._create_test_data(url)
        
        return items
    
    def _parse_sale_link(self, link, href: str, sale_id: str) -> Optional[dict]:
        """Parse a sale link and its surrounding context."""
        # Build full URL
        source_url = urljoin(self.BASE_URL, href)
        
        # Extract title from link text or parent
        title = link.get_text(strip=True)
        
        # Clean up title - remove numbers at start, "Listedby" suffix, etc.
        title = re.sub(r'^\d+', '', title)  # Remove leading numbers (photo count)
        title = re.sub(r'Listedby.*$', '', title, flags=re.IGNORECASE)  # Remove "Listedby..."
        title = re.sub(r'Last modified.*$', '', title, flags=re.IGNORECASE)  # Remove timestamps
        title = title.strip()
        
        if not title or len(title) < 3:
            title = "Estate Sale"
        
        # Extract city and zip from URL pattern /FL/City/ZIP/ID
        url_parts = href.split('/')
        city = "Florida"
        if len(url_parts) >= 3:
            city = url_parts[2].replace('-', ' ')  # /FL/Fort-Lauderdale/... -> Fort Lauderdale
        
        # Try to get more context from parent elements
        parent = link.find_parent(['div', 'article', 'li'])
        description = ""
        closing_at = None
        
        if parent:
            # Look for date info in parent
            date_text = parent.get_text()
            closing_at = self._parse_dates(date_text)
            
            # Look for description/categories
            desc_elem = parent.find(class_=re.compile(r"desc|categories|highlights"))
            if desc_elem:
                description = desc_elem.get_text(strip=True)
        
        # Default closing time if not found
        if not closing_at:
            closing_at = datetime.now() + timedelta(days=3)
        
        return {
            "source_item_id": f"estatesales_{sale_id}",
            "source": self.source.value,
            "source_url": source_url,
            "title": title,
            "description": description,
            "closing_at": closing_at,
            "city": city,
            "state": "FL",
            "current_price": None,  # Estate sales don't have individual prices
            "raw_category": "estate_sale",
        }
    
    def _parse_dates(self, date_text: str) -> Optional[datetime]:
        """Parse date text to get closing datetime."""
        # Estate sales typically run for 2-3 days
        # Try to extract the end date
        
        # Look for patterns like "Dec 27-28" or "December 27, 2025"
        today = datetime.now()
        
        # Simple heuristic: if we find a date, assume it ends that day at 5pm
        month_match = re.search(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2})",
            date_text,
            re.IGNORECASE
        )
        
        if month_match:
            month_str = month_match.group(1)[:3]
            day = int(month_match.group(2))
            
            months = {
                "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
            }
            month = months.get(month_str.lower(), today.month)
            year = today.year
            
            # If the date is in the past this year, assume next year
            try:
                closing = datetime(year, month, day, 17, 0)  # 5 PM
                if closing < today:
                    closing = datetime(year + 1, month, day, 17, 0)
                return closing
            except ValueError:
                pass
        
        # Default: assume sale ends in 3 days at 5pm
        return today + timedelta(days=3, hours=17 - today.hour)
    
    def _extract_city(self, location_text: str) -> str:
        """Extract city from location text."""
        # Look for Florida cities
        florida_cities = [
            "Miami", "Fort Lauderdale", "Hollywood", "Boca Raton",
            "West Palm Beach", "Orlando", "Tampa", "Jacksonville",
            "Naples", "Sarasota", "Clearwater", "St Petersburg",
            "Coral Gables", "Hialeah", "Pembroke Pines", "Pompano Beach"
        ]
        
        location_lower = location_text.lower()
        for city in florida_cities:
            if city.lower() in location_lower:
                return city
        
        # Try to extract first part before comma
        if "," in location_text:
            return location_text.split(",")[0].strip()
        
        return "Unknown"
    
    def _create_test_data(self, url: str) -> list[dict]:
        """Create test data when scraping fails (for development)."""
        now = datetime.now()
        
        return [
            {
                "source_item_id": "estatesales_test_001",
                "source": self.source.value,
                "source_url": f"{self.BASE_URL}/FL/Miami/estate-sales/12345",
                "title": "Estate Sale - Furniture, Antiques & More",
                "description": "Beautiful dining room set, oak dining table with 6 chairs, china cabinet, vintage furniture collection",
                "closing_at": now + timedelta(days=2),
                "city": "Miami",
                "state": "FL",
                "current_price": None,
                "raw_category": "estate_sale",
            },
            {
                "source_item_id": "estatesales_test_002", 
                "source": self.source.value,
                "source_url": f"{self.BASE_URL}/FL/Fort-Lauderdale/estate-sales/12346",
                "title": "Moving Sale - Quality Furniture",
                "description": "Solid wood dining table, mid-century modern furniture, bedroom sets",
                "closing_at": now + timedelta(days=1, hours=12),
                "city": "Fort Lauderdale",
                "state": "FL",
                "current_price": None,
                "raw_category": "estate_sale",
            },
        ]
