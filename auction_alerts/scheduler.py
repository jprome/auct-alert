"""
Scheduler module for Auction Alerts.

Uses APScheduler to run the pipeline on a schedule:
- Every 4 hours: Scrape and check for matches
- Daily: Update expired alerts and run learning loop

Can also be run manually via command line.
"""

import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .pipeline import run_full_pipeline, run_outcome_update

logger = logging.getLogger(__name__)


def create_scheduler() -> BlockingScheduler:
    """
    Create and configure the APScheduler.
    
    Jobs:
    1. scrape_and_alert: Every 4 hours - fetch new listings and send alerts
    2. update_outcomes: Daily at midnight - update expired alerts
    3. learning_loop: Daily at 1am - analyze and adjust parameters
    
    Returns:
        Configured BlockingScheduler
    """
    scheduler = BlockingScheduler()
    
    # Job 1: Scrape and send alerts every 4 hours
    scheduler.add_job(
        run_full_pipeline,
        trigger=IntervalTrigger(hours=4),
        id="scrape_and_alert",
        name="Scrape auctions and send alerts",
        replace_existing=True,
        max_instances=1,
    )
    
    # Job 2: Update expired alerts daily at midnight
    scheduler.add_job(
        run_outcome_update,
        trigger=CronTrigger(hour=0, minute=0),
        id="update_outcomes",
        name="Update expired alerts",
        replace_existing=True,
        max_instances=1,
    )
    
    # Job 3: Run learning loop daily at 1am
    scheduler.add_job(
        run_learning_loop_job,
        trigger=CronTrigger(hour=1, minute=0),
        id="learning_loop",
        name="Analyze outcomes and adjust parameters",
        replace_existing=True,
        max_instances=1,
    )
    
    logger.info("Scheduler configured with 3 jobs")
    return scheduler


def run_learning_loop_job() -> None:
    """Wrapper for learning loop to handle logging."""
    from .outcomes import run_learning_loop
    
    logger.info("Starting learning loop analysis...")
    try:
        changes = run_learning_loop(days=7)
        if changes:
            logger.info(f"Learning loop made {len(changes)} changes: {changes}")
        else:
            logger.info("Learning loop made no changes")
    except Exception as e:
        logger.error(f"Learning loop failed: {e}")


def start_scheduler() -> None:
    """Start the scheduler (blocking)."""
    scheduler = create_scheduler()
    
    logger.info("Starting Auction Alerts scheduler...")
    logger.info("Press Ctrl+C to stop")
    
    # Run initial scrape immediately
    logger.info("Running initial pipeline...")
    try:
        run_full_pipeline()
    except Exception as e:
        logger.error(f"Initial pipeline failed: {e}")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    """CLI entry point for the scheduler."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Auction Alerts Scheduler")
    parser.add_argument(
        "--mode",
        choices=["schedule", "once", "outcomes", "learn"],
        default="schedule",
        help="Mode to run: schedule (continuous), once (single run), outcomes (update expired), learn (run learning loop)"
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
    
    if args.mode == "schedule":
        start_scheduler()
    elif args.mode == "once":
        logger.info("Running single pipeline execution...")
        run_full_pipeline()
    elif args.mode == "outcomes":
        logger.info("Updating expired alerts...")
        run_outcome_update()
    elif args.mode == "learn":
        logger.info("Running learning loop...")
        run_learning_loop_job()


if __name__ == "__main__":
    main()
