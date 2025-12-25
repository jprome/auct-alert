"""
Data models for Auction Alerts.

Defines canonical dataclasses that all sources normalize into.
These models represent the unified schema for items, alerts, and outcomes.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
from enum import Enum
import json


class ItemCategory(str, Enum):
    """Categories for auction items."""
    FURNITURE = "furniture"
    ELECTRONICS = "electronics"
    APPLIANCES = "appliances"
    COLLECTIBLES = "collectibles"
    VEHICLES = "vehicles"
    TOOLS = "tools"
    OTHER = "other"


class ItemSubtype(str, Enum):
    """Subtypes for furniture category (extend as needed)."""
    DINING_TABLE = "dining_table"
    DINING_CHAIR = "dining_chair"
    SOFA = "sofa"
    BED = "bed"
    DRESSER = "dresser"
    DESK = "desk"
    BOOKSHELF = "bookshelf"
    CABINET = "cabinet"
    OTHER = "other"


class AuctionSource(str, Enum):
    """Supported auction data sources."""
    ESTATESALES_NET = "estatesales_net"
    HIBID = "hibid"
    FLORIDA_SURPLUS = "florida_surplus"


class AlertOutcome(str, Enum):
    """Possible outcomes for an alert."""
    PENDING = "pending"       # Alert sent, waiting for action
    CLICKED = "clicked"       # User clicked the link
    IGNORED = "ignored"       # No click before auction closed
    EXPIRED = "expired"       # Auction closed
    WON = "won"              # User won the auction (manual input)
    LOST = "lost"            # User bid but didn't win


@dataclass
class Location:
    """Geographic location for pickup."""
    city: str
    state: str = "FL"  # Default to Florida
    lat: Optional[float] = None
    lng: Optional[float] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Location":
        return cls(
            city=data.get("city", "Unknown"),
            state=data.get("state", "FL"),
            lat=data.get("lat"),
            lng=data.get("lng"),
        )


@dataclass
class AuctionItem:
    """
    Canonical representation of an auction item.
    
    This is the unified schema that all sources normalize into.
    All fields are designed to support the intent matching logic.
    """
    # Unique identifier (source-specific ID prefixed with source name)
    item_id: str
    
    # Source information
    source: AuctionSource
    source_url: str
    
    # Item details
    title: str
    description: str = ""
    category: ItemCategory = ItemCategory.OTHER
    subtype: ItemSubtype = ItemSubtype.OTHER
    
    # Pricing
    current_price: Optional[float] = None
    starting_price: Optional[float] = None
    buy_now_price: Optional[float] = None
    
    # Timing
    closing_at: Optional[datetime] = None
    
    # Location
    pickup_location: Optional[Location] = None
    
    # Tracking timestamps
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    
    # Raw data reference (for debugging)
    raw_data_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        data = {
            "item_id": self.item_id,
            "source": self.source.value,
            "source_url": self.source_url,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "subtype": self.subtype.value,
            "current_price": self.current_price,
            "starting_price": self.starting_price,
            "buy_now_price": self.buy_now_price,
            "closing_at": self.closing_at.isoformat() if self.closing_at else None,
            "pickup_location": self.pickup_location.to_dict() if self.pickup_location else None,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "raw_data_id": self.raw_data_id,
        }
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "AuctionItem":
        """Create from dictionary (e.g., from database)."""
        return cls(
            item_id=data["item_id"],
            source=AuctionSource(data["source"]),
            source_url=data["source_url"],
            title=data["title"],
            description=data.get("description", ""),
            category=ItemCategory(data.get("category", "other")),
            subtype=ItemSubtype(data.get("subtype", "other")),
            current_price=data.get("current_price"),
            starting_price=data.get("starting_price"),
            buy_now_price=data.get("buy_now_price"),
            closing_at=datetime.fromisoformat(data["closing_at"]) if data.get("closing_at") else None,
            pickup_location=Location.from_dict(data["pickup_location"]) if data.get("pickup_location") else None,
            first_seen=datetime.fromisoformat(data["first_seen"]) if data.get("first_seen") else datetime.utcnow(),
            last_seen=datetime.fromisoformat(data["last_seen"]) if data.get("last_seen") else datetime.utcnow(),
            raw_data_id=data.get("raw_data_id"),
        )


@dataclass
class UserIntent:
    """
    User's search intent / preferences.
    
    For the MVP, we hardcode a single intent. Later this can be
    extended to support multiple users with different preferences.
    """
    intent_id: str
    user_id: str
    user_email: str
    
    # What they're looking for
    category: ItemCategory = ItemCategory.FURNITURE
    subtype: Optional[ItemSubtype] = ItemSubtype.DINING_TABLE
    keywords: list[str] = field(default_factory=lambda: ["dining", "table"])
    
    # Constraints
    max_price: float = 1200.0
    max_distance_miles: float = 100.0
    
    # Reference location (lat, lng)
    reference_lat: float = 25.7617  # Miami
    reference_lng: float = -80.1918
    
    # Timing preferences
    min_hours_before_close: int = 2   # Don't alert if <2 hours left
    max_hours_before_close: int = 48  # Alert if closing within 48 hours
    
    # Alert settings
    confidence_threshold: float = 0.6  # Minimum confidence to send alert
    
    # Learning loop adjustable parameters
    is_active: bool = True
    
    def to_dict(self) -> dict:
        return {
            "intent_id": self.intent_id,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "category": self.category.value,
            "subtype": self.subtype.value if self.subtype else None,
            "keywords": self.keywords,
            "max_price": self.max_price,
            "max_distance_miles": self.max_distance_miles,
            "reference_lat": self.reference_lat,
            "reference_lng": self.reference_lng,
            "min_hours_before_close": self.min_hours_before_close,
            "max_hours_before_close": self.max_hours_before_close,
            "confidence_threshold": self.confidence_threshold,
            "is_active": self.is_active,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "UserIntent":
        return cls(
            intent_id=data["intent_id"],
            user_id=data["user_id"],
            user_email=data["user_email"],
            category=ItemCategory(data.get("category", "furniture")),
            subtype=ItemSubtype(data["subtype"]) if data.get("subtype") else None,
            keywords=data.get("keywords", []),
            max_price=data.get("max_price", 1200.0),
            max_distance_miles=data.get("max_distance_miles", 100.0),
            reference_lat=data.get("reference_lat", 25.7617),
            reference_lng=data.get("reference_lng", -80.1918),
            min_hours_before_close=data.get("min_hours_before_close", 2),
            max_hours_before_close=data.get("max_hours_before_close", 48),
            confidence_threshold=data.get("confidence_threshold", 0.6),
            is_active=data.get("is_active", True),
        )


@dataclass
class Alert:
    """
    Record of an alert sent to a user.
    
    Tracks the alert lifecycle from sent → clicked/ignored → outcome.
    """
    alert_id: str
    item_id: str
    intent_id: str
    user_id: str
    
    # Match details
    confidence_score: float
    match_reasons: list[str] = field(default_factory=list)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    
    # Outcome tracking
    outcome: AlertOutcome = AlertOutcome.PENDING
    outcome_updated_at: Optional[datetime] = None
    
    # Tracking
    tracking_token: str = ""  # Unique token for click tracking
    
    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "item_id": self.item_id,
            "intent_id": self.intent_id,
            "user_id": self.user_id,
            "confidence_score": self.confidence_score,
            "match_reasons": self.match_reasons,
            "created_at": self.created_at.isoformat(),
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "clicked_at": self.clicked_at.isoformat() if self.clicked_at else None,
            "outcome": self.outcome.value,
            "outcome_updated_at": self.outcome_updated_at.isoformat() if self.outcome_updated_at else None,
            "tracking_token": self.tracking_token,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Alert":
        return cls(
            alert_id=data["alert_id"],
            item_id=data["item_id"],
            intent_id=data["intent_id"],
            user_id=data["user_id"],
            confidence_score=data["confidence_score"],
            match_reasons=data.get("match_reasons", []),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            sent_at=datetime.fromisoformat(data["sent_at"]) if data.get("sent_at") else None,
            clicked_at=datetime.fromisoformat(data["clicked_at"]) if data.get("clicked_at") else None,
            outcome=AlertOutcome(data.get("outcome", "pending")),
            outcome_updated_at=datetime.fromisoformat(data["outcome_updated_at"]) if data.get("outcome_updated_at") else None,
            tracking_token=data.get("tracking_token", ""),
        )


@dataclass
class LearningParameter:
    """
    Tracks a parameter that can be adjusted by the learning loop.
    
    Keeps history of changes so they can be reversed.
    """
    param_name: str
    current_value: float
    previous_value: Optional[float] = None
    change_reason: str = ""
    changed_at: Optional[datetime] = None
    
    # Bounds to prevent runaway adjustments
    min_value: float = 0.0
    max_value: float = float('inf')
    step_size: float = 0.1  # Default adjustment step
    
    def to_dict(self) -> dict:
        return {
            "param_name": self.param_name,
            "current_value": self.current_value,
            "previous_value": self.previous_value,
            "change_reason": self.change_reason,
            "changed_at": self.changed_at.isoformat() if self.changed_at else None,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "step_size": self.step_size,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "LearningParameter":
        return cls(
            param_name=data["param_name"],
            current_value=data["current_value"],
            previous_value=data.get("previous_value"),
            change_reason=data.get("change_reason", ""),
            changed_at=datetime.fromisoformat(data["changed_at"]) if data.get("changed_at") else None,
            min_value=data.get("min_value", 0.0),
            max_value=data.get("max_value", float('inf')),
            step_size=data.get("step_size", 0.1),
        )
