"""
Supabase database integration module.

Handles all database operations:
- Storing raw HTML/JSON from scrapers
- Saving normalized auction items
- Managing alerts and outcomes
- Tracking learning parameters

Tables required (see setup_supabase.sql):
- raw_data: Stores raw HTML/JSON from each source
- items: Normalized auction items
- users: Users who receive alerts
- intents: User search intents/preferences
- alerts: Sent alerts with outcome tracking
- learning_params: Adjustable parameters for learning loop
- learning_history: History of parameter changes
"""

import json
import logging
from datetime import datetime
from typing import Optional
from supabase import create_client, Client

from .config import get_supabase_config
from .models import (
    AuctionItem, 
    UserIntent, 
    Alert, 
    AlertOutcome,
    LearningParameter,
    AuctionSource,
)

logger = logging.getLogger(__name__)


class Database:
    """
    Supabase database client wrapper.
    
    Provides methods for all database operations needed by the auction alerts system.
    """
    
    def __init__(self):
        """Initialize Supabase client."""
        config = get_supabase_config()
        if not config.url or not config.key:
            raise ValueError("Supabase URL and key must be set in environment variables")
        self._client: Client = create_client(config.url, config.key)
    
    @property
    def client(self) -> Client:
        """Get the Supabase client."""
        return self._client
    
    # =========================================================================
    # RAW DATA OPERATIONS
    # =========================================================================
    
    def store_raw_data(
        self, 
        source: AuctionSource, 
        url: str, 
        content: str, 
        content_type: str = "html"
    ) -> str:
        """
        Store raw HTML/JSON from a scraper.
        
        Args:
            source: The auction source (e.g., ESTATESALES_NET)
            url: The URL that was scraped
            content: The raw HTML or JSON content
            content_type: "html" or "json"
            
        Returns:
            The ID of the stored raw data record
        """
        data = {
            "source": source.value,
            "url": url,
            "content": content,
            "content_type": content_type,
            "scraped_at": datetime.utcnow().isoformat(),
        }
        
        result = self._client.table("raw_data").insert(data).execute()
        raw_id = result.data[0]["id"]
        logger.info(f"Stored raw {content_type} from {source.value}: {raw_id}")
        return raw_id
    
    def get_raw_data(self, raw_id: str) -> Optional[dict]:
        """Get raw data by ID."""
        result = self._client.table("raw_data").select("*").eq("id", raw_id).execute()
        return result.data[0] if result.data else None
    
    # =========================================================================
    # ITEM OPERATIONS
    # =========================================================================
    
    def upsert_item(self, item: AuctionItem) -> str:
        """
        Insert or update an auction item.
        
        If the item_id already exists, updates the record and last_seen.
        Otherwise, creates a new record.
        
        Returns:
            The item_id
        """
        item_dict = item.to_dict()
        
        # Convert pickup_location to JSON string for storage
        if item_dict.get("pickup_location"):
            item_dict["pickup_location"] = json.dumps(item_dict["pickup_location"])
        
        # Check if item exists
        existing = self._client.table("items").select("item_id").eq("item_id", item.item_id).execute()
        
        if existing.data:
            # Update existing - keep first_seen, update last_seen
            item_dict.pop("first_seen", None)
            item_dict["last_seen"] = datetime.utcnow().isoformat()
            self._client.table("items").update(item_dict).eq("item_id", item.item_id).execute()
            logger.debug(f"Updated item: {item.item_id}")
        else:
            # Insert new
            self._client.table("items").insert(item_dict).execute()
            logger.info(f"Inserted new item: {item.item_id}")
        
        return item.item_id
    
    def get_item(self, item_id: str) -> Optional[AuctionItem]:
        """Get an item by ID."""
        result = self._client.table("items").select("*").eq("item_id", item_id).execute()
        if not result.data:
            return None
        
        data = result.data[0]
        # Parse pickup_location from JSON
        if data.get("pickup_location"):
            data["pickup_location"] = json.loads(data["pickup_location"])
        
        return AuctionItem.from_dict(data)
    
    def get_active_items(
        self, 
        category: Optional[str] = None,
        source: Optional[str] = None,
        closing_after: Optional[datetime] = None,
    ) -> list[AuctionItem]:
        """
        Get active auction items (not yet closed).
        
        Args:
            category: Filter by category
            source: Filter by source
            closing_after: Only items closing after this time
            
        Returns:
            List of AuctionItem objects
        """
        query = self._client.table("items").select("*")
        
        if category:
            query = query.eq("category", category)
        if source:
            query = query.eq("source", source)
        if closing_after:
            query = query.gt("closing_at", closing_after.isoformat())
        
        result = query.execute()
        
        items = []
        for data in result.data:
            if data.get("pickup_location"):
                data["pickup_location"] = json.loads(data["pickup_location"])
            items.append(AuctionItem.from_dict(data))
        
        return items
    
    # =========================================================================
    # USER & INTENT OPERATIONS
    # =========================================================================
    
    def create_user(self, user_id: str, email: str, name: str = "") -> str:
        """Create a new user."""
        data = {
            "id": user_id,
            "email": email,
            "name": name,
            "created_at": datetime.utcnow().isoformat(),
            "is_active": True,
        }
        self._client.table("users").insert(data).execute()
        logger.info(f"Created user: {user_id}")
        return user_id
    
    def get_user(self, user_id: str) -> Optional[dict]:
        """Get user by ID."""
        result = self._client.table("users").select("*").eq("id", user_id).execute()
        return result.data[0] if result.data else None
    
    def upsert_intent(self, intent: UserIntent) -> str:
        """Insert or update a user intent."""
        intent_dict = intent.to_dict()
        intent_dict["keywords"] = json.dumps(intent_dict["keywords"])
        
        # Check if exists
        existing = self._client.table("intents").select("intent_id").eq("intent_id", intent.intent_id).execute()
        
        if existing.data:
            self._client.table("intents").update(intent_dict).eq("intent_id", intent.intent_id).execute()
            logger.debug(f"Updated intent: {intent.intent_id}")
        else:
            self._client.table("intents").insert(intent_dict).execute()
            logger.info(f"Created intent: {intent.intent_id}")
        
        return intent.intent_id
    
    def get_active_intents(self) -> list[UserIntent]:
        """Get all active user intents."""
        result = self._client.table("intents").select("*").eq("is_active", True).execute()
        
        intents = []
        for data in result.data:
            if data.get("keywords"):
                data["keywords"] = json.loads(data["keywords"])
            intents.append(UserIntent.from_dict(data))
        
        return intents
    
    # =========================================================================
    # ALERT OPERATIONS
    # =========================================================================
    
    def create_alert(self, alert: Alert) -> str:
        """Create a new alert record."""
        alert_dict = alert.to_dict()
        alert_dict["match_reasons"] = json.dumps(alert_dict["match_reasons"])
        
        self._client.table("alerts").insert(alert_dict).execute()
        logger.info(f"Created alert: {alert.alert_id} for item {alert.item_id}")
        return alert.alert_id
    
    def update_alert_sent(self, alert_id: str) -> None:
        """Mark alert as sent."""
        self._client.table("alerts").update({
            "sent_at": datetime.utcnow().isoformat()
        }).eq("alert_id", alert_id).execute()
    
    def update_alert_clicked(self, tracking_token: str) -> Optional[str]:
        """
        Mark alert as clicked (called when user clicks tracking link).
        
        Returns:
            The alert_id if found, None otherwise
        """
        result = self._client.table("alerts").select("alert_id").eq("tracking_token", tracking_token).execute()
        
        if not result.data:
            return None
        
        alert_id = result.data[0]["alert_id"]
        self._client.table("alerts").update({
            "clicked_at": datetime.utcnow().isoformat(),
            "outcome": AlertOutcome.CLICKED.value,
            "outcome_updated_at": datetime.utcnow().isoformat(),
        }).eq("alert_id", alert_id).execute()
        
        logger.info(f"Alert clicked: {alert_id}")
        return alert_id
    
    def update_alert_outcome(self, alert_id: str, outcome: AlertOutcome) -> None:
        """Update the outcome of an alert."""
        self._client.table("alerts").update({
            "outcome": outcome.value,
            "outcome_updated_at": datetime.utcnow().isoformat(),
        }).eq("alert_id", alert_id).execute()
        logger.info(f"Updated alert {alert_id} outcome to {outcome.value}")
    
    def get_pending_alerts(self) -> list[Alert]:
        """Get all alerts with pending outcome."""
        result = self._client.table("alerts").select("*").eq("outcome", "pending").execute()
        
        alerts = []
        for data in result.data:
            if data.get("match_reasons"):
                data["match_reasons"] = json.loads(data["match_reasons"])
            alerts.append(Alert.from_dict(data))
        
        return alerts
    
    def get_alerts_for_analysis(self, days: int = 14) -> list[Alert]:
        """Get alerts from the last N days for analysis."""
        cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0)
        from datetime import timedelta
        cutoff = cutoff - timedelta(days=days)
        
        result = self._client.table("alerts").select("*").gt("created_at", cutoff.isoformat()).execute()
        
        alerts = []
        for data in result.data:
            if data.get("match_reasons"):
                data["match_reasons"] = json.loads(data["match_reasons"])
            alerts.append(Alert.from_dict(data))
        
        return alerts
    
    def check_alert_exists(self, item_id: str, intent_id: str) -> bool:
        """Check if an alert already exists for this item-intent pair."""
        result = self._client.table("alerts").select("alert_id").eq("item_id", item_id).eq("intent_id", intent_id).execute()
        return len(result.data) > 0
    
    # =========================================================================
    # LEARNING PARAMETER OPERATIONS
    # =========================================================================
    
    def get_learning_param(self, param_name: str) -> Optional[LearningParameter]:
        """Get a learning parameter by name."""
        result = self._client.table("learning_params").select("*").eq("param_name", param_name).execute()
        
        if not result.data:
            return None
        
        return LearningParameter.from_dict(result.data[0])
    
    def upsert_learning_param(self, param: LearningParameter) -> None:
        """Insert or update a learning parameter."""
        param_dict = param.to_dict()
        
        existing = self._client.table("learning_params").select("param_name").eq("param_name", param.param_name).execute()
        
        if existing.data:
            self._client.table("learning_params").update(param_dict).eq("param_name", param.param_name).execute()
        else:
            self._client.table("learning_params").insert(param_dict).execute()
        
        logger.info(f"Updated learning param: {param.param_name} = {param.current_value}")
    
    def log_param_change(
        self, 
        param_name: str, 
        old_value: float, 
        new_value: float, 
        reason: str
    ) -> None:
        """Log a parameter change to history."""
        data = {
            "param_name": param_name,
            "old_value": old_value,
            "new_value": new_value,
            "reason": reason,
            "changed_at": datetime.utcnow().isoformat(),
        }
        self._client.table("learning_history").insert(data).execute()
        logger.info(f"Logged param change: {param_name} {old_value} -> {new_value} ({reason})")
    
    def get_param_history(self, param_name: str, limit: int = 10) -> list[dict]:
        """Get recent history for a parameter."""
        result = self._client.table("learning_history").select("*").eq("param_name", param_name).order("changed_at", desc=True).limit(limit).execute()
        return result.data


# Global database instance (lazy loaded)
_db: Optional[Database] = None


def get_db() -> Database:
    """Get database instance (singleton)."""
    global _db
    if _db is None:
        _db = Database()
    return _db
