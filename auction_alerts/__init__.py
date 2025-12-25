"""
Auction Alerts - 14-Day Minimum Value Loop

A system that turns messy fragmented auction data into actionable alerts.
Focuses on estate/furniture auctions in Florida.

Modules:
- config: Configuration and environment variables
- models: Canonical data models (dataclasses)
- db: Supabase integration for storage
- sources: Scrapers for different auction sources
- normalization: Map source data to canonical schema
- intent_matching: Match items against user intents
- alerts: Send email alerts
- outcomes: Track outcomes and implement learning loop
- scheduler: APScheduler setup for daily runs
- pipeline: Main orchestration
- tracking_server: Click tracking server
"""

__version__ = "0.1.0"

# Convenient imports
from .models import (
    AuctionItem,
    AuctionSource,
    ItemCategory,
    ItemSubtype,
    Location,
    UserIntent,
    Alert,
    AlertOutcome,
    LearningParameter,
)
from .normalization import normalize_items, ItemNormalizer
from .intent_matching import find_matches, IntentMatcher, MatchResult
from .alerts import send_alerts, AlertSender
from .outcomes import (
    update_expired_alerts,
    get_outcome_stats,
    run_learning_loop,
    record_click,
    OutcomeStats,
)
from .pipeline import run_full_pipeline, setup_default_user_and_intent

__all__ = [
    # Models
    "AuctionItem",
    "AuctionSource", 
    "ItemCategory",
    "ItemSubtype",
    "Location",
    "UserIntent",
    "Alert",
    "AlertOutcome",
    "LearningParameter",
    # Normalization
    "normalize_items",
    "ItemNormalizer",
    # Intent Matching
    "find_matches",
    "IntentMatcher",
    "MatchResult",
    # Alerts
    "send_alerts",
    "AlertSender",
    # Outcomes
    "update_expired_alerts",
    "get_outcome_stats",
    "run_learning_loop",
    "record_click",
    "OutcomeStats",
    # Pipeline
    "run_full_pipeline",
    "setup_default_user_and_intent",
]
