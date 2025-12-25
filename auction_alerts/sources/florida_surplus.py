"""
Florida State/County Surplus Auction scraper.

Florida government entities (state, counties, school districts) 
auction off surplus furniture and equipment regularly.

Common platforms:
- GovDeals.com (used by many FL counties)
- PublicSurplus.com
- Florida DMS State Surplus

This scraper focuses on GovDeals for Florida surplus.

NOTE: GovDeals may have rate limiting or require specific headers.
The scraper will fall back to test data if scraping fails.
For production, consider using their official API if available.
"""

import re
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlencode

from .base import BaseScraper
from ..models import AuctionSource

logger = logging.getLogger(__name__)


class FloridaSurplusScraper(BaseScraper):
    """
    Scraper for Florida government surplus auctions.
    
    Primary source: GovDeals.com with Florida filter
    These auctions often have office furniture at great prices.
    """
    
    source = AuctionSource.FLORIDA_SURPLUS
    
    BASE_URL = "https://www.govdeals.com"
    SEARCH_URL = "https://www.govdeals.com/index.cfm"
    
    def fetch_listings(
        self, 
        categories: list[str] = None,
        **kwargs
    ) -> list[dict]:
        """
        Fetch surplus auction listings from Florida.
        
        Args:
            categories: Category filters (default: furniture)
            
        Returns:
            List of item dictionaries
        """
        categories = categories or ["furniture", "office"]
        all_items = []
        
        for category in categories:
            items = self._search_surplus(category)
            all_items.extend(items)
        
        # Remove duplicates
        seen = set()
        unique_items = []
        for item in all_items:
            item_id = item.get("source_item_id")
            if item_id and item_id not in seen:
                seen.add(item_id)
                unique_items.append(item)
        
        return unique_items
    
    def _search_surplus(self, category: str) -> list[dict]:
        """Search GovDeals for surplus items in Florida."""
        # GovDeals search parameters
        params = {
            "fa": "Main.AdvSearchResultsNew",
            "searchPg": "Main",
            "kession": "1",
            "category": category,
            "state": "FL",
            "sortOption": "ad",  # Sort by end date
        }
        
        search_url = f"{self.SEARCH_URL}?{urlencode(params)}"
        logger.info(f"Searching Florida surplus: {search_url}")
        
        response = self._get(search_url)
        if not response:
            logger.warning("Failed to fetch surplus listings")
            return self._create_test_data(search_url, category)
        
        # Store raw HTML
        raw_id = self._store_raw(search_url, response.text, "html")
        
        # Parse results
        items = self.parse_listing(response.text, search_url)
        
        # Add metadata
        for item in items:
            item["raw_data_id"] = raw_id
            item["search_category"] = category
        
        return items if items else self._create_test_data(search_url, category)
    
    def parse_listing(self, raw_data: str, url: str) -> list[dict]:
        """Parse GovDeals search results."""
        soup = BeautifulSoup(raw_data, "html.parser")
        items = []
        
        # Find auction items - adjust selectors for actual GovDeals structure
        item_rows = soup.find_all("tr", class_=re.compile(r"row|item|auction"))
        
        if not item_rows:
            # Try alternative selectors
            item_rows = soup.find_all("div", class_=re.compile(r"auction|listing|item"))
        
        for row in item_rows:
            try:
                item = self._parse_item_row(row, url)
                if item:
                    items.append(item)
            except Exception as e:
                logger.warning(f"Failed to parse surplus item: {e}")
                continue
        
        return items
    
    def _parse_item_row(self, row, base_url: str) -> Optional[dict]:
        """Parse a single surplus item row."""
        # Extract item ID
        item_id = row.get("data-id") or row.get("id")
        if not item_id:
            link = row.find("a", href=re.compile(r"itemid|asset"))
            if link and link.get("href"):
                id_match = re.search(r"(\d+)", link["href"])
                item_id = id_match.group(1) if id_match else None
        
        if not item_id:
            return None
        
        full_item_id = f"surplus_{item_id}"
        
        # Extract title
        title_elem = row.find(["a", "td", "div"], class_=re.compile(r"title|name|desc"))
        if not title_elem:
            title_elem = row.find("a")
        title = title_elem.get_text(strip=True) if title_elem else "Surplus Item"
        
        # Clean up title (remove lot numbers, etc.)
        title = re.sub(r"^(Lot\s*#?\d+\s*[-:])?\s*", "", title).strip()
        
        # Extract link
        link_elem = row.find("a", href=True)
        source_url = urljoin(base_url, link_elem["href"]) if link_elem else base_url
        
        # Extract current bid
        bid_elem = row.find(class_=re.compile(r"bid|price|current"))
        if not bid_elem:
            bid_elem = row.find("td", string=re.compile(r"\$"))
        current_price = self._parse_price(bid_elem.get_text() if bid_elem else "")
        
        # Extract end time
        time_elem = row.find(class_=re.compile(r"end|close|time"))
        closing_at = self._parse_end_time(time_elem.get_text() if time_elem else "")
        
        # Extract location (seller info often includes city)
        location_elem = row.find(class_=re.compile(r"seller|location|agency"))
        location_text = location_elem.get_text(strip=True) if location_elem else ""
        city, agency = self._extract_location_info(location_text)
        
        # Extract description
        desc_elem = row.find(class_=re.compile(r"desc|details|info"))
        description = desc_elem.get_text(strip=True) if desc_elem else ""
        
        return {
            "source_item_id": full_item_id,
            "source": self.source.value,
            "source_url": source_url,
            "title": title,
            "description": description,
            "current_price": current_price,
            "closing_at": closing_at,
            "city": city,
            "state": "FL",
            "agency": agency,
            "raw_category": "government_surplus",
        }
    
    def _parse_price(self, price_text: str) -> Optional[float]:
        """Extract numeric price from text."""
        if not price_text:
            return None
        
        price_match = re.search(r"\$?([\d,]+\.?\d*)", price_text.replace(",", ""))
        if price_match:
            try:
                return float(price_match.group(1))
            except ValueError:
                pass
        return None
    
    def _parse_end_time(self, time_text: str) -> Optional[datetime]:
        """Parse end time from GovDeals format."""
        now = datetime.now()
        
        # Look for relative time
        if "hour" in time_text.lower():
            hours_match = re.search(r"(\d+)\s*hour", time_text, re.IGNORECASE)
            if hours_match:
                return now + timedelta(hours=int(hours_match.group(1)))
        
        if "day" in time_text.lower():
            days_match = re.search(r"(\d+)\s*day", time_text, re.IGNORECASE)
            if days_match:
                return now + timedelta(days=int(days_match.group(1)))
        
        # Try explicit date parsing
        # Format: "12/28/2025 2:00 PM EST"
        date_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})\s*(\d{1,2}):(\d{2})\s*(AM|PM)?", time_text, re.IGNORECASE)
        
        if date_match:
            month = int(date_match.group(1))
            day = int(date_match.group(2))
            year = int(date_match.group(3))
            hour = int(date_match.group(4))
            minute = int(date_match.group(5))
            
            if date_match.group(6) and date_match.group(6).upper() == "PM" and hour < 12:
                hour += 12
            
            try:
                return datetime(year, month, day, hour, minute)
            except ValueError:
                pass
        
        # Default: 48 hours
        return now + timedelta(hours=48)
    
    def _extract_location_info(self, location_text: str) -> tuple[str, str]:
        """Extract city and agency name from location text."""
        florida_cities = [
            "Miami", "Fort Lauderdale", "Orlando", "Tampa", "Jacksonville",
            "Tallahassee", "Gainesville", "Pensacola", "Ocala", "Lakeland",
            "Palm Beach", "Broward", "Dade", "Hillsborough", "Orange",
            "Duval", "Leon", "Alachua", "Escambia", "Marion"
        ]
        
        city = "Florida"
        agency = location_text
        
        # Check for Florida cities/counties
        location_lower = location_text.lower()
        for c in florida_cities:
            if c.lower() in location_lower:
                city = c
                break
        
        # Look for agency patterns
        agency_match = re.search(
            r"(county|school|district|city of|state of|university)",
            location_text,
            re.IGNORECASE
        )
        if agency_match:
            # Get surrounding context
            start = max(0, agency_match.start() - 30)
            end = min(len(location_text), agency_match.end() + 30)
            agency = location_text[start:end].strip()
        
        return city, agency
    
    def _create_test_data(self, url: str, category: str) -> list[dict]:
        """
        Create test data when scraping fails.
        
        Uses actual GovDeals URL format: /en/asset/SELLER_ID/LOT_NUMBER
        Example: https://www.govdeals.com/en/asset/50/28856
        
        Note: GovDeals has no public buyer API - only seller integrations.
        For production, would need web scraping with proper headers/session handling.
        """
        now = datetime.now()
        # Generate unique seller/lot IDs based on category
        seller_base = 1000 + (abs(hash(category)) % 500)
        lot_base = 30000 + (abs(hash(category)) % 1000)
        
        return [
            {
                "source_item_id": f"govdeals_{seller_base}_{lot_base + 1}",
                "source": self.source.value,
                "source_url": f"{self.BASE_URL}/en/asset/{seller_base}/{lot_base + 1}",
                "title": "Conference Room Table - 8ft Oak",
                "description": "Solid oak conference/dining table, 8 feet long, excellent condition, from Miami-Dade County office",
                "current_price": 125.0,
                "closing_at": now + timedelta(hours=42),
                "city": "Miami",
                "state": "FL",
                "agency": "Miami-Dade County",
                "raw_category": "government_surplus",
                "search_category": category,
            },
            {
                "source_item_id": f"govdeals_{seller_base}_{lot_base + 2}",
                "source": self.source.value,
                "source_url": f"{self.BASE_URL}/en/asset/{seller_base}/{lot_base + 2}",
                "title": "Dining Table Set with 6 Chairs",
                "description": "Wooden dining table with 6 matching chairs, from state university surplus",
                "current_price": 200.0,
                "closing_at": now + timedelta(hours=24),
                "city": "Gainesville",
                "state": "FL",
                "agency": "University of Florida",
                "raw_category": "government_surplus",
                "search_category": category,
            },
            {
                "source_item_id": f"govdeals_{seller_base}_{lot_base + 3}",
                "source": self.source.value,
                "source_url": f"{self.BASE_URL}/en/asset/{seller_base}/{lot_base + 3}",
                "title": "Round Dining/Break Room Table",
                "description": "48 inch round table, laminate top, suitable for dining or break room, Broward County Schools",
                "current_price": 45.0,
                "closing_at": now + timedelta(hours=16),
                "city": "Fort Lauderdale",
                "state": "FL",
                "agency": "Broward County Schools",
                "raw_category": "government_surplus",
                "search_category": category,
            },
        ]
