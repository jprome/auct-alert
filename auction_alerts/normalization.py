"""
Normalization module for Auction Alerts.

Maps raw scraped data from different sources into the canonical AuctionItem schema.
Each source has different field names and formats - this module handles all the mapping.
"""

import re
import logging
from datetime import datetime
from typing import Optional

from .models import (
    AuctionItem,
    AuctionSource,
    ItemCategory,
    ItemSubtype,
    Location,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CITY COORDINATES (Florida cities for distance calculations)
# =============================================================================

FLORIDA_CITY_COORDS: dict[str, tuple[float, float]] = {
    # Major metros
    "Miami": (25.7617, -80.1918),
    "Fort Lauderdale": (26.1224, -80.1373),
    "Hollywood": (26.0112, -80.1495),
    "Boca Raton": (26.3587, -80.0831),
    "West Palm Beach": (26.7153, -80.0534),
    "Orlando": (28.5383, -81.3792),
    "Tampa": (27.9506, -82.4572),
    "Jacksonville": (30.3322, -81.6557),
    "Naples": (26.1420, -81.7948),
    "Sarasota": (27.3364, -82.5307),
    "Clearwater": (27.9659, -82.8001),
    "St Petersburg": (27.7676, -82.6403),
    # Other Florida cities
    "Coral Gables": (25.7215, -80.2684),
    "Hialeah": (25.8576, -80.2781),
    "Pembroke Pines": (26.0128, -80.3379),
    "Pompano Beach": (26.2379, -80.1248),
    "Gainesville": (29.6516, -82.3248),
    "Tallahassee": (30.4383, -84.2807),
    "Pensacola": (30.4213, -87.2169),
    "Ocala": (29.1872, -82.1401),
    "Lakeland": (28.0395, -81.9498),
    # Default for "Florida" or unknown
    "Florida": (27.6648, -81.5158),  # Center of FL
    "Unknown": (25.7617, -80.1918),  # Default to Miami
}


# =============================================================================
# KEYWORD MAPPINGS FOR CATEGORY/SUBTYPE DETECTION
# =============================================================================

FURNITURE_KEYWORDS = [
    "furniture", "table", "chair", "sofa", "couch", "desk", "bed", "dresser",
    "cabinet", "bookshelf", "bookcase", "armoire", "hutch", "credenza",
    "ottoman", "bench", "stool", "nightstand", "wardrobe"
]

SUBTYPE_KEYWORDS: dict[ItemSubtype, list[str]] = {
    ItemSubtype.DINING_TABLE: [
        "dining table", "dining room table", "kitchen table", "breakfast table",
        "conference table", "extension table", "pedestal table", "farm table",
        "farmhouse table", "trestle table", "drop leaf table"
    ],
    ItemSubtype.DINING_CHAIR: [
        "dining chair", "side chair", "arm chair", "captain chair",
        "parsons chair", "windsor chair"
    ],
    ItemSubtype.SOFA: [
        "sofa", "couch", "loveseat", "sectional", "settee", "chesterfield"
    ],
    ItemSubtype.BED: [
        "bed frame", "headboard", "footboard", "platform bed", "sleigh bed",
        "poster bed", "murphy bed", "daybed"
    ],
    ItemSubtype.DRESSER: [
        "dresser", "chest of drawers", "bureau", "highboy", "lowboy"
    ],
    ItemSubtype.DESK: [
        "desk", "writing desk", "executive desk", "computer desk", "roll top"
    ],
    ItemSubtype.BOOKSHELF: [
        "bookshelf", "bookcase", "shelving", "etagere", "curio"
    ],
    ItemSubtype.CABINET: [
        "cabinet", "china cabinet", "hutch", "armoire", "buffet", "sideboard",
        "credenza", "entertainment center", "tv stand"
    ],
}


# =============================================================================
# NORMALIZER CLASS
# =============================================================================

class ItemNormalizer:
    """
    Normalizes raw scraped data into canonical AuctionItem objects.
    
    Usage:
        normalizer = ItemNormalizer()
        items = normalizer.normalize_batch(raw_items)
    """
    
    def normalize_batch(self, raw_items: list[dict]) -> list[AuctionItem]:
        """
        Normalize a batch of raw items.
        
        Args:
            raw_items: List of raw item dictionaries from scrapers
            
        Returns:
            List of normalized AuctionItem objects
        """
        normalized = []
        
        for raw in raw_items:
            try:
                item = self.normalize(raw)
                if item:
                    normalized.append(item)
            except Exception as e:
                logger.warning(f"Failed to normalize item {raw.get('source_item_id', 'unknown')}: {e}")
                continue
        
        logger.info(f"Normalized {len(normalized)}/{len(raw_items)} items")
        return normalized
    
    def normalize(self, raw: dict) -> Optional[AuctionItem]:
        """
        Normalize a single raw item into an AuctionItem.
        
        Args:
            raw: Raw item dictionary from scraper
            
        Returns:
            AuctionItem or None if normalization fails
        """
        # Required fields check
        if not raw.get("source_item_id") or not raw.get("source"):
            logger.warning(f"Missing required fields in raw item: {raw}")
            return None
        
        # Parse source
        try:
            source = AuctionSource(raw["source"])
        except ValueError:
            logger.warning(f"Unknown source: {raw['source']}")
            return None
        
        # Build item_id (globally unique)
        item_id = raw["source_item_id"]
        
        # Extract and clean text fields
        title = self._clean_text(raw.get("title", "Unknown Item"))
        description = self._clean_text(raw.get("description", ""))
        
        # Detect category and subtype from title/description
        combined_text = f"{title} {description}".lower()
        category = self._detect_category(combined_text)
        subtype = self._detect_subtype(combined_text)
        
        # Parse price
        current_price = self._parse_price(raw.get("current_price"))
        starting_price = self._parse_price(raw.get("starting_price"))
        buy_now_price = self._parse_price(raw.get("buy_now_price"))
        
        # Parse closing time
        closing_at = self._parse_datetime(raw.get("closing_at"))
        
        # Build location
        location = self._build_location(raw)
        
        # Parse timestamps
        first_seen = self._parse_datetime(raw.get("first_seen")) or datetime.utcnow()
        last_seen = self._parse_datetime(raw.get("last_seen")) or datetime.utcnow()
        
        return AuctionItem(
            item_id=item_id,
            source=source,
            source_url=raw.get("source_url", ""),
            title=title,
            description=description,
            category=category,
            subtype=subtype,
            current_price=current_price,
            starting_price=starting_price,
            buy_now_price=buy_now_price,
            closing_at=closing_at,
            pickup_location=location,
            first_seen=first_seen,
            last_seen=last_seen,
            raw_data_id=raw.get("raw_data_id"),
        )
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)
        # Remove HTML entities
        text = re.sub(r"&[a-z]+;", " ", text)
        # Strip
        return text.strip()
    
    def _detect_category(self, text: str) -> ItemCategory:
        """Detect item category from text."""
        text_lower = text.lower()
        
        # Check for furniture keywords
        for keyword in FURNITURE_KEYWORDS:
            if keyword in text_lower:
                return ItemCategory.FURNITURE
        
        # Could add more categories here
        return ItemCategory.OTHER
    
    def _detect_subtype(self, text: str) -> ItemSubtype:
        """Detect item subtype from text."""
        text_lower = text.lower()
        
        # Check each subtype's keywords
        for subtype, keywords in SUBTYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return subtype
        
        # Default for furniture without specific subtype
        return ItemSubtype.OTHER
    
    def _parse_price(self, value) -> Optional[float]:
        """Parse price from various formats."""
        if value is None:
            return None
        
        if isinstance(value, (int, float)):
            return float(value) if value > 0 else None
        
        if isinstance(value, str):
            # Remove currency symbols and commas
            cleaned = re.sub(r"[,$]", "", value)
            try:
                price = float(cleaned)
                return price if price > 0 else None
            except ValueError:
                return None
        
        return None
    
    def _parse_datetime(self, value) -> Optional[datetime]:
        """Parse datetime from various formats."""
        if value is None:
            return None
        
        if isinstance(value, datetime):
            return value
        
        if isinstance(value, str):
            # Try ISO format first
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
            
            # Try common formats
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%m/%d/%Y %H:%M",
                "%m/%d/%Y",
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        
        return None
    
    def _build_location(self, raw: dict) -> Optional[Location]:
        """Build Location object from raw data."""
        city = raw.get("city", "")
        state = raw.get("state", "FL")
        
        if not city:
            return None
        
        # Get coordinates for known cities
        lat, lng = FLORIDA_CITY_COORDS.get(
            city, 
            FLORIDA_CITY_COORDS.get("Unknown")
        )
        
        return Location(
            city=city,
            state=state,
            lat=lat,
            lng=lng,
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def normalize_items(raw_items: list[dict]) -> list[AuctionItem]:
    """
    Convenience function to normalize items.
    
    Args:
        raw_items: List of raw item dictionaries
        
    Returns:
        List of normalized AuctionItem objects
    """
    normalizer = ItemNormalizer()
    return normalizer.normalize_batch(raw_items)


def get_city_coordinates(city: str) -> tuple[float, float]:
    """
    Get coordinates for a Florida city.
    
    Args:
        city: City name
        
    Returns:
        Tuple of (lat, lng)
    """
    return FLORIDA_CITY_COORDS.get(city, FLORIDA_CITY_COORDS["Unknown"])
