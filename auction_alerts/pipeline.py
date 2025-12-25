"""
Main Pipeline module for Auction Alerts.

Orchestrates the full data flow:
1. Scrape → Fetch raw data from all sources
2. Normalize → Map to canonical schema
3. Store → Save items to Supabase
4. Match → Find items matching user intents
5. Alert → Send email alerts
6. Log → Record outcomes

This is the main entry point for running the pipeline.
"""

import logging
from datetime import datetime
from typing import Optional

from .config import get_app_config
from .db import get_db
from .models import AuctionItem, UserIntent, ItemCategory, ItemSubtype
from .sources import EstateSalesScraper, HiBidScraper, FloridaSurplusScraper
from .normalization import normalize_items
from .intent_matching import find_matches, MatchResult
from .alerts import send_alerts
from .outcomes import update_expired_alerts, run_learning_loop, LearningLoop

logger = logging.getLogger(__name__)


# =============================================================================
# PIPELINE FUNCTIONS
# =============================================================================

def scrape_all_sources() -> list[dict]:
    """
    Scrape all auction sources.
    
    Returns:
        List of raw item dictionaries from all sources
    """
    all_items = []
    
    # EstateSales.net
    try:
        logger.info("Scraping EstateSales.net...")
        scraper = EstateSalesScraper()
        items = scraper.scrape(cities=["Miami", "Fort-Lauderdale", "Boca-Raton"])
        all_items.extend(items)
        logger.info(f"Got {len(items)} items from EstateSales.net")
    except Exception as e:
        logger.error(f"EstateSales scrape failed: {e}")
    
    # HiBid
    try:
        logger.info("Scraping HiBid...")
        scraper = HiBidScraper()
        items = scraper.scrape(keywords=["dining table", "furniture", "table"])
        all_items.extend(items)
        logger.info(f"Got {len(items)} items from HiBid")
    except Exception as e:
        logger.error(f"HiBid scrape failed: {e}")
    
    # Florida Surplus
    try:
        logger.info("Scraping Florida Surplus...")
        scraper = FloridaSurplusScraper()
        items = scraper.scrape(categories=["furniture", "office"])
        all_items.extend(items)
        logger.info(f"Got {len(items)} items from Florida Surplus")
    except Exception as e:
        logger.error(f"Florida Surplus scrape failed: {e}")
    
    logger.info(f"Total scraped: {len(all_items)} items from all sources")
    return all_items


def store_items(items: list[AuctionItem]) -> int:
    """
    Store normalized items in Supabase.
    
    Args:
        items: List of normalized AuctionItem objects
        
    Returns:
        Number of items stored/updated
    """
    db = get_db()
    stored = 0
    
    for item in items:
        try:
            db.upsert_item(item)
            stored += 1
        except Exception as e:
            logger.warning(f"Failed to store item {item.item_id}: {e}")
    
    logger.info(f"Stored {stored}/{len(items)} items")
    return stored


def get_active_intents() -> list[UserIntent]:
    """
    Get all active user intents.
    
    For the MVP, if no intents exist in the database,
    returns a hardcoded default intent.
    
    Returns:
        List of UserIntent objects
    """
    db = get_db()
    intents = db.get_active_intents()
    
    if not intents:
        logger.warning("No intents in database, using default intent")
        # Get current learning parameters for threshold
        loop = LearningLoop()
        loop.initialize_params()
        threshold = loop.get_current_param("confidence_threshold")
        
        intents = [create_default_intent(threshold)]
    
    return intents


def create_default_intent(confidence_threshold: float = 0.6) -> UserIntent:
    """
    Create the default hardcoded intent for the MVP.
    
    Intent: Dining table, furniture category, max $1200, 
    within 100 miles of Miami, closing within 48 hours.
    
    Args:
        confidence_threshold: Minimum confidence to alert
        
    Returns:
        UserIntent object
    """
    return UserIntent(
        intent_id="default_intent_001",
        user_id="default_user",
        user_email="test@example.com",  # Replace with your email for testing
        category=ItemCategory.FURNITURE,
        subtype=ItemSubtype.DINING_TABLE,
        keywords=["dining", "table", "dining table"],
        max_price=1200.0,
        max_distance_miles=100.0,
        reference_lat=25.7617,  # Miami
        reference_lng=-80.1918,
        min_hours_before_close=2,
        max_hours_before_close=48,
        confidence_threshold=confidence_threshold,
        is_active=True,
    )


def run_full_pipeline() -> dict:
    """
    Run the complete pipeline: scrape → normalize → store → match → alert.
    
    Returns:
        Summary dict with counts and status
    """
    start_time = datetime.utcnow()
    logger.info(f"Starting pipeline run at {start_time}")
    
    summary = {
        "started_at": start_time.isoformat(),
        "scraped": 0,
        "normalized": 0,
        "stored": 0,
        "matches": 0,
        "alerts_sent": 0,
        "errors": [],
    }
    
    try:
        # Step 1: Scrape all sources
        raw_items = scrape_all_sources()
        summary["scraped"] = len(raw_items)
        
        if not raw_items:
            logger.warning("No items scraped - pipeline complete")
            return summary
        
        # Step 2: Normalize items
        normalized = normalize_items(raw_items)
        summary["normalized"] = len(normalized)
        
        # Step 3: Store in database
        stored = store_items(normalized)
        summary["stored"] = stored
        
        # Step 4: Get active intents
        intents = get_active_intents()
        logger.info(f"Matching against {len(intents)} intents")
        
        # Step 5: Find matches
        matches = find_matches(normalized, intents)
        summary["matches"] = len(matches)
        
        if matches:
            logger.info(f"Found {len(matches)} matches, sending alerts...")
            
            # Step 6: Send alerts
            sent_alerts = send_alerts(matches)
            summary["alerts_sent"] = len(sent_alerts)
        else:
            logger.info("No matches found")
        
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        summary["errors"].append(str(e))
    
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    summary["duration_seconds"] = duration
    summary["completed_at"] = end_time.isoformat()
    
    logger.info(f"Pipeline complete in {duration:.1f}s: {summary}")
    return summary


def run_outcome_update() -> dict:
    """
    Update expired alerts and return summary.
    
    Returns:
        Summary dict with counts
    """
    logger.info("Running outcome update...")
    
    try:
        expired_count = update_expired_alerts()
        return {
            "expired_updated": expired_count,
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Outcome update failed: {e}")
        return {
            "expired_updated": 0,
            "status": "error",
            "error": str(e)
        }


# =============================================================================
# SETUP FUNCTIONS
# =============================================================================

def setup_default_user_and_intent(email: str) -> dict:
    """
    Set up a default user and intent in Supabase.
    
    Call this once to initialize the system with your email.
    
    Args:
        email: Your email address for receiving alerts
        
    Returns:
        Dict with created user_id and intent_id
    """
    import uuid
    
    db = get_db()
    
    # Create user
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    db.create_user(user_id, email, "Test User")
    
    # Create intent
    intent = create_default_intent()
    intent.intent_id = f"intent_{uuid.uuid4().hex[:8]}"
    intent.user_id = user_id
    intent.user_email = email
    
    db.upsert_intent(intent)
    
    # Initialize learning parameters
    loop = LearningLoop()
    loop.initialize_params()
    
    logger.info(f"Created user {user_id} and intent {intent.intent_id}")
    
    return {
        "user_id": user_id,
        "intent_id": intent.intent_id,
        "email": email,
    }


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    """CLI entry point for running the pipeline."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Auction Alerts Pipeline")
    parser.add_argument(
        "--setup",
        metavar="EMAIL",
        help="Set up default user with this email address"
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the full pipeline once"
    )
    parser.add_argument(
        "--outcomes",
        action="store_true",
        help="Update expired alerts"
    )
    parser.add_argument(
        "--learn",
        action="store_true",
        help="Run learning loop"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    if args.setup:
        result = setup_default_user_and_intent(args.setup)
        print(f"Setup complete: {result}")
    elif args.run:
        result = run_full_pipeline()
        print(f"Pipeline complete: {result}")
    elif args.outcomes:
        result = run_outcome_update()
        print(f"Outcomes updated: {result}")
    elif args.learn:
        changes = run_learning_loop()
        print(f"Learning loop changes: {changes}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
