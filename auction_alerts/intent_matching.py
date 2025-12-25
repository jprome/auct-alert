"""
Intent Matching module for Auction Alerts.

Matches normalized auction items against user intents to find relevant items.
Computes a confidence score based on how well an item matches the intent criteria.
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

from .models import (
    AuctionItem,
    UserIntent,
    ItemCategory,
    ItemSubtype,
)

logger = logging.getLogger(__name__)


# =============================================================================
# MATCH RESULT
# =============================================================================

@dataclass
class MatchResult:
    """
    Result of matching an item against an intent.
    
    Contains the confidence score and reasons for the match.
    """
    item: AuctionItem
    intent: UserIntent
    confidence_score: float
    match_reasons: list[str]
    is_match: bool  # True if score >= threshold
    
    # Individual scores for debugging/learning
    category_score: float = 0.0
    subtype_score: float = 0.0
    keyword_score: float = 0.0
    price_score: float = 0.0
    distance_score: float = 0.0
    timing_score: float = 0.0


# =============================================================================
# INTENT MATCHER
# =============================================================================

class IntentMatcher:
    """
    Matches auction items against user intents.
    
    Scoring weights can be adjusted by the learning loop.
    
    Usage:
        matcher = IntentMatcher()
        matches = matcher.match_items(items, intents)
    """
    
    # Default scoring weights (can be overridden)
    WEIGHTS = {
        "category": 0.20,    # Must be correct category
        "subtype": 0.25,     # Specific item type
        "keyword": 0.15,     # Keywords in title/description
        "price": 0.20,       # Within price range
        "distance": 0.10,    # Within distance
        "timing": 0.10,      # Closing soon but not too soon
    }
    
    def __init__(self, weights: Optional[dict] = None):
        """Initialize matcher with optional custom weights."""
        self.weights = weights or self.WEIGHTS.copy()
    
    def match_items(
        self, 
        items: list[AuctionItem], 
        intents: list[UserIntent]
    ) -> list[MatchResult]:
        """
        Match a list of items against a list of intents.
        
        Args:
            items: List of normalized AuctionItem objects
            intents: List of UserIntent objects to match against
            
        Returns:
            List of MatchResult objects for matches above threshold
        """
        matches = []
        
        for item in items:
            for intent in intents:
                if not intent.is_active:
                    continue
                
                result = self.match(item, intent)
                if result.is_match:
                    matches.append(result)
        
        # Sort by confidence score descending
        matches.sort(key=lambda m: m.confidence_score, reverse=True)
        
        logger.info(f"Found {len(matches)} matches from {len(items)} items and {len(intents)} intents")
        return matches
    
    def match(self, item: AuctionItem, intent: UserIntent) -> MatchResult:
        """
        Match a single item against a single intent.
        
        Args:
            item: The auction item to evaluate
            intent: The user intent to match against
            
        Returns:
            MatchResult with scores and reasons
        """
        reasons = []
        
        # Calculate individual scores
        category_score = self._score_category(item, intent, reasons)
        subtype_score = self._score_subtype(item, intent, reasons)
        keyword_score = self._score_keywords(item, intent, reasons)
        price_score = self._score_price(item, intent, reasons)
        distance_score = self._score_distance(item, intent, reasons)
        timing_score = self._score_timing(item, intent, reasons)
        
        # Calculate weighted total
        total_score = (
            self.weights["category"] * category_score +
            self.weights["subtype"] * subtype_score +
            self.weights["keyword"] * keyword_score +
            self.weights["price"] * price_score +
            self.weights["distance"] * distance_score +
            self.weights["timing"] * timing_score
        )
        
        # Normalize to 0-1 range
        confidence = min(1.0, max(0.0, total_score))
        
        is_match = confidence >= intent.confidence_threshold
        
        return MatchResult(
            item=item,
            intent=intent,
            confidence_score=confidence,
            match_reasons=reasons,
            is_match=is_match,
            category_score=category_score,
            subtype_score=subtype_score,
            keyword_score=keyword_score,
            price_score=price_score,
            distance_score=distance_score,
            timing_score=timing_score,
        )
    
    def _score_category(
        self, 
        item: AuctionItem, 
        intent: UserIntent, 
        reasons: list
    ) -> float:
        """Score category match (0 or 1)."""
        if item.category == intent.category:
            reasons.append(f"Category match: {item.category.value}")
            return 1.0
        return 0.0
    
    def _score_subtype(
        self, 
        item: AuctionItem, 
        intent: UserIntent, 
        reasons: list
    ) -> float:
        """Score subtype match (0, 0.5, or 1)."""
        if intent.subtype is None:
            # No subtype requirement
            return 0.5
        
        if item.subtype == intent.subtype:
            reasons.append(f"Subtype match: {item.subtype.value}")
            return 1.0
        
        # Partial match for "other" subtype in furniture
        if (item.category == ItemCategory.FURNITURE and 
            intent.category == ItemCategory.FURNITURE and
            item.subtype == ItemSubtype.OTHER):
            return 0.3
        
        return 0.0
    
    def _score_keywords(
        self, 
        item: AuctionItem, 
        intent: UserIntent, 
        reasons: list
    ) -> float:
        """Score keyword matches in title and description."""
        if not intent.keywords:
            return 0.5  # No keywords specified
        
        text = f"{item.title} {item.description}".lower()
        matches = 0
        matched_keywords = []
        
        for keyword in intent.keywords:
            if keyword.lower() in text:
                matches += 1
                matched_keywords.append(keyword)
        
        if matched_keywords:
            reasons.append(f"Keywords found: {', '.join(matched_keywords)}")
        
        # Score is proportion of keywords found
        return matches / len(intent.keywords) if intent.keywords else 0.5
    
    def _score_price(
        self, 
        item: AuctionItem, 
        intent: UserIntent, 
        reasons: list
    ) -> float:
        """Score price within budget."""
        if item.current_price is None:
            # Unknown price - give partial score
            reasons.append("Price unknown")
            return 0.5
        
        if item.current_price <= intent.max_price:
            # Calculate how good the price is (lower = better)
            ratio = item.current_price / intent.max_price
            score = 1.0 - (ratio * 0.5)  # Score 0.5-1.0 based on how far under budget
            reasons.append(f"Price ${item.current_price:.0f} within ${intent.max_price:.0f} budget")
            return score
        else:
            # Over budget - steep penalty
            overage_ratio = item.current_price / intent.max_price
            if overage_ratio < 1.2:
                # Slightly over - small penalty
                reasons.append(f"Price ${item.current_price:.0f} slightly over ${intent.max_price:.0f}")
                return 0.3
            return 0.0
    
    def _score_distance(
        self, 
        item: AuctionItem, 
        intent: UserIntent, 
        reasons: list
    ) -> float:
        """Score distance from reference location."""
        if item.pickup_location is None or item.pickup_location.lat is None:
            # Unknown location - partial score
            reasons.append("Location unknown")
            return 0.5
        
        distance = self._calculate_distance(
            intent.reference_lat, intent.reference_lng,
            item.pickup_location.lat, item.pickup_location.lng
        )
        
        if distance <= intent.max_distance_miles:
            # Within range - score based on closeness
            ratio = distance / intent.max_distance_miles
            score = 1.0 - (ratio * 0.5)  # Score 0.5-1.0
            reasons.append(f"Distance {distance:.0f} miles from reference")
            return score
        else:
            # Out of range
            return 0.0
    
    def _score_timing(
        self, 
        item: AuctionItem, 
        intent: UserIntent, 
        reasons: list
    ) -> float:
        """Score timing (closing within window but not too soon)."""
        if item.closing_at is None:
            reasons.append("Closing time unknown")
            return 0.5
        
        now = datetime.utcnow()
        hours_until_close = (item.closing_at - now).total_seconds() / 3600
        
        if hours_until_close < 0:
            # Already closed
            return 0.0
        
        if hours_until_close < intent.min_hours_before_close:
            # Too soon - not enough time to act
            reasons.append(f"Closing too soon ({hours_until_close:.1f}h)")
            return 0.2
        
        if hours_until_close <= intent.max_hours_before_close:
            # In the sweet spot
            # Prefer items closing sooner (more urgent)
            urgency = 1.0 - (hours_until_close / intent.max_hours_before_close)
            score = 0.5 + (urgency * 0.5)  # Score 0.5-1.0
            reasons.append(f"Closing in {hours_until_close:.1f} hours")
            return score
        else:
            # Too far out
            reasons.append(f"Closing in {hours_until_close:.0f} hours (outside {intent.max_hours_before_close}h window)")
            return 0.3
    
    def _calculate_distance(
        self, 
        lat1: float, lng1: float, 
        lat2: float, lng2: float
    ) -> float:
        """
        Calculate distance in miles using Haversine formula.
        
        Args:
            lat1, lng1: First point coordinates
            lat2, lng2: Second point coordinates
            
        Returns:
            Distance in miles
        """
        # Earth's radius in miles
        R = 3959
        
        # Convert to radians
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)
        
        # Haversine formula
        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) * 
             math.sin(delta_lng / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def find_matches(
    items: list[AuctionItem], 
    intents: list[UserIntent],
    weights: Optional[dict] = None
) -> list[MatchResult]:
    """
    Convenience function to find matching items.
    
    Args:
        items: List of auction items
        intents: List of user intents
        weights: Optional custom scoring weights
        
    Returns:
        List of MatchResult objects
    """
    matcher = IntentMatcher(weights=weights)
    return matcher.match_items(items, intents)


def calculate_distance_miles(
    lat1: float, lng1: float,
    lat2: float, lng2: float
) -> float:
    """
    Calculate distance between two points in miles.
    
    Convenience wrapper around the Haversine calculation.
    """
    matcher = IntentMatcher()
    return matcher._calculate_distance(lat1, lng1, lat2, lng2)
