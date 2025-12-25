"""
Click Tracking Server for Auction Alerts.

A simple Flask server that:
1. Handles click tracking when users click alert links
2. Records clicks in Supabase
3. Redirects to the actual auction URL

Run this server alongside the scheduler to enable click tracking.
"""

import logging
from flask import Flask, redirect, abort

from .db import get_db
from .outcomes import record_click

logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/click/<tracking_token>")
def handle_click(tracking_token: str):
    """
    Handle a click on an alert tracking link.
    
    1. Record the click in Supabase
    2. Get the original auction URL
    3. Redirect the user to the auction
    """
    db = get_db()
    
    # Record the click
    alert_id = record_click(tracking_token)
    
    if not alert_id:
        logger.warning(f"Invalid tracking token: {tracking_token}")
        abort(404)
    
    # Get the alert to find the item URL
    result = db.client.table("alerts").select("item_id").eq("alert_id", alert_id).execute()
    if not result.data:
        abort(404)
    
    item_id = result.data[0]["item_id"]
    
    # Get the item URL
    item = db.get_item(item_id)
    if not item:
        abort(404)
    
    logger.info(f"Click recorded for alert {alert_id}, redirecting to {item.source_url}")
    
    return redirect(item.source_url)


@app.route("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


def run_server(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    """Run the Flask server."""
    app.run(host=host, port=port, debug=debug)


def main():
    """CLI entry point for the tracking server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Auction Alerts Click Tracking Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    logger.info(f"Starting click tracking server on {args.host}:{args.port}")
    run_server(args.host, args.port, args.debug)


if __name__ == "__main__":
    main()
