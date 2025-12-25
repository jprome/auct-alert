"""
Outcomes and Learning Loop module for Auction Alerts.

Handles:
1. Tracking alert outcomes (clicked/ignored/expired)
2. Analyzing outcome patterns
3. Adjusting parameters based on outcomes (learning loop)

The learning loop is simple and reversible:
- If click rate is low, adjust one parameter
- Log all changes so they can be reversed
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

from .db import get_db
from .models import Alert, AlertOutcome, LearningParameter

logger = logging.getLogger(__name__)


# =============================================================================
# OUTCOME ANALYSIS
# =============================================================================

@dataclass
class OutcomeStats:
    """Statistics about alert outcomes for a time period."""
    total_alerts: int = 0
    clicked: int = 0
    ignored: int = 0
    expired: int = 0
    pending: int = 0
    
    @property
    def click_rate(self) -> float:
        """Click rate as a decimal (0-1)."""
        closed = self.clicked + self.ignored + self.expired
        if closed == 0:
            return 0.0
        return self.clicked / closed
    
    @property
    def response_rate(self) -> float:
        """Response rate (clicked vs pending/ignored)."""
        total_sent = self.clicked + self.ignored + self.pending
        if total_sent == 0:
            return 0.0
        return self.clicked / total_sent


class OutcomeTracker:
    """
    Tracks and analyzes alert outcomes.
    
    Usage:
        tracker = OutcomeTracker()
        tracker.update_expired_alerts()
        stats = tracker.get_stats(days=7)
    """
    
    def __init__(self):
        self.db = get_db()
    
    def update_expired_alerts(self) -> int:
        """
        Update alerts for expired auctions.
        
        Checks pending alerts and marks them as expired if their
        associated auction has closed.
        
        Returns:
            Number of alerts marked as expired
        """
        pending = self.db.get_pending_alerts()
        expired_count = 0
        now = datetime.utcnow()
        
        for alert in pending:
            # Get the associated item
            item = self.db.get_item(alert.item_id)
            
            if item and item.closing_at and item.closing_at < now:
                # Auction has closed
                if alert.clicked_at:
                    # User clicked but didn't do anything else
                    outcome = AlertOutcome.EXPIRED
                else:
                    # User never clicked
                    outcome = AlertOutcome.IGNORED
                
                self.db.update_alert_outcome(alert.alert_id, outcome)
                expired_count += 1
        
        logger.info(f"Updated {expired_count} expired alerts")
        return expired_count
    
    def record_click(self, tracking_token: str) -> Optional[str]:
        """
        Record a click on an alert tracking link.
        
        Args:
            tracking_token: The unique tracking token from the email link
            
        Returns:
            The alert_id if found, None otherwise
        """
        return self.db.update_alert_clicked(tracking_token)
    
    def get_stats(self, days: int = 14) -> OutcomeStats:
        """
        Get outcome statistics for the past N days.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            OutcomeStats object
        """
        alerts = self.db.get_alerts_for_analysis(days)
        
        stats = OutcomeStats(total_alerts=len(alerts))
        
        for alert in alerts:
            if alert.outcome == AlertOutcome.CLICKED:
                stats.clicked += 1
            elif alert.outcome == AlertOutcome.IGNORED:
                stats.ignored += 1
            elif alert.outcome == AlertOutcome.EXPIRED:
                stats.expired += 1
            else:
                stats.pending += 1
        
        return stats


# =============================================================================
# LEARNING LOOP
# =============================================================================

# Parameters that can be adjusted by the learning loop
ADJUSTABLE_PARAMS = {
    "confidence_threshold": {
        "default": 0.6,
        "min": 0.3,
        "max": 0.9,
        "step": 0.05,
        "description": "Minimum confidence score to send an alert",
    },
    "max_hours_before_close": {
        "default": 48,
        "min": 12,
        "max": 96,
        "step": 6,
        "description": "Maximum hours before closing to send alert",
    },
    "max_distance_miles": {
        "default": 100,
        "min": 25,
        "max": 200,
        "step": 10,
        "description": "Maximum distance from reference location",
    },
    "max_price": {
        "default": 1200,
        "min": 300,
        "max": 3000,
        "step": 100,
        "description": "Maximum price to consider",
    },
}


class LearningLoop:
    """
    Simple learning loop that adjusts one parameter based on outcomes.
    
    Rules:
    1. If click rate < 20%, we're sending too many irrelevant alerts
       → Increase confidence threshold
    2. If click rate > 50%, we might be missing good items
       → Consider decreasing threshold or expanding criteria
    3. Only change one parameter at a time
    4. Log all changes so they can be reversed
    
    Usage:
        loop = LearningLoop()
        changes = loop.analyze_and_adjust()
    """
    
    # Target click rate range
    TARGET_CLICK_RATE_MIN = 0.20
    TARGET_CLICK_RATE_MAX = 0.50
    
    # Minimum alerts before making adjustments
    MIN_ALERTS_FOR_ANALYSIS = 10
    
    def __init__(self):
        self.db = get_db()
    
    def initialize_params(self) -> None:
        """Initialize learning parameters with defaults if they don't exist."""
        for name, config in ADJUSTABLE_PARAMS.items():
            existing = self.db.get_learning_param(name)
            if not existing:
                param = LearningParameter(
                    param_name=name,
                    current_value=config["default"],
                    min_value=config["min"],
                    max_value=config["max"],
                    step_size=config["step"],
                )
                self.db.upsert_learning_param(param)
                logger.info(f"Initialized param {name} = {config['default']}")
    
    def get_current_param(self, name: str) -> float:
        """Get current value of a parameter."""
        param = self.db.get_learning_param(name)
        if param:
            return param.current_value
        return ADJUSTABLE_PARAMS.get(name, {}).get("default", 0)
    
    def analyze_and_adjust(self, days: int = 7) -> list[dict]:
        """
        Analyze recent outcomes and make adjustments if needed.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            List of changes made (empty if no changes)
        """
        changes = []
        
        # Get outcome stats
        tracker = OutcomeTracker()
        stats = tracker.get_stats(days)
        
        logger.info(f"Outcome stats ({days} days): {stats.total_alerts} alerts, "
                   f"{stats.click_rate:.1%} click rate")
        
        # Need minimum alerts to make decisions
        if stats.total_alerts < self.MIN_ALERTS_FOR_ANALYSIS:
            logger.info(f"Not enough alerts for analysis (need {self.MIN_ALERTS_FOR_ANALYSIS})")
            return changes
        
        click_rate = stats.click_rate
        
        # Decision logic
        if click_rate < self.TARGET_CLICK_RATE_MIN:
            # Too many irrelevant alerts - be more selective
            change = self._adjust_param(
                "confidence_threshold",
                direction="up",
                reason=f"Click rate {click_rate:.1%} below target {self.TARGET_CLICK_RATE_MIN:.0%}"
            )
            if change:
                changes.append(change)
        
        elif click_rate > self.TARGET_CLICK_RATE_MAX:
            # Missing good items - be less selective
            change = self._adjust_param(
                "confidence_threshold",
                direction="down",
                reason=f"Click rate {click_rate:.1%} above target {self.TARGET_CLICK_RATE_MAX:.0%}"
            )
            if change:
                changes.append(change)
        else:
            logger.info(f"Click rate {click_rate:.1%} is in target range - no adjustment needed")
        
        return changes
    
    def _adjust_param(
        self, 
        param_name: str, 
        direction: str,
        reason: str
    ) -> Optional[dict]:
        """
        Adjust a parameter up or down by its step size.
        
        Args:
            param_name: Name of the parameter
            direction: "up" or "down"
            reason: Reason for the change
            
        Returns:
            Change record or None if at bounds
        """
        param = self.db.get_learning_param(param_name)
        if not param:
            logger.warning(f"Parameter {param_name} not found")
            return None
        
        old_value = param.current_value
        
        if direction == "up":
            new_value = min(param.max_value, old_value + param.step_size)
        else:
            new_value = max(param.min_value, old_value - param.step_size)
        
        if new_value == old_value:
            logger.info(f"Parameter {param_name} already at bound ({old_value})")
            return None
        
        # Update parameter
        param.previous_value = old_value
        param.current_value = new_value
        param.change_reason = reason
        param.changed_at = datetime.utcnow()
        
        self.db.upsert_learning_param(param)
        self.db.log_param_change(param_name, old_value, new_value, reason)
        
        change = {
            "param": param_name,
            "old_value": old_value,
            "new_value": new_value,
            "direction": direction,
            "reason": reason,
        }
        
        logger.info(f"Adjusted {param_name}: {old_value} → {new_value} ({reason})")
        return change
    
    def revert_last_change(self, param_name: str) -> Optional[dict]:
        """
        Revert the last change to a parameter.
        
        Args:
            param_name: Name of the parameter
            
        Returns:
            Revert record or None if can't revert
        """
        param = self.db.get_learning_param(param_name)
        if not param or param.previous_value is None:
            logger.warning(f"Cannot revert {param_name} - no previous value")
            return None
        
        old_value = param.current_value
        new_value = param.previous_value
        
        param.current_value = new_value
        param.previous_value = old_value  # So we can re-revert if needed
        param.change_reason = "Reverted previous change"
        param.changed_at = datetime.utcnow()
        
        self.db.upsert_learning_param(param)
        self.db.log_param_change(param_name, old_value, new_value, "Manual revert")
        
        logger.info(f"Reverted {param_name}: {old_value} → {new_value}")
        
        return {
            "param": param_name,
            "old_value": old_value,
            "new_value": new_value,
            "action": "revert",
        }
    
    def get_param_history(self, param_name: str, limit: int = 10) -> list[dict]:
        """Get history of changes for a parameter."""
        return self.db.get_param_history(param_name, limit)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def update_expired_alerts() -> int:
    """Update expired alerts and return count."""
    tracker = OutcomeTracker()
    return tracker.update_expired_alerts()


def get_outcome_stats(days: int = 14) -> OutcomeStats:
    """Get outcome statistics for the past N days."""
    tracker = OutcomeTracker()
    return tracker.get_stats(days)


def run_learning_loop(days: int = 7) -> list[dict]:
    """Run the learning loop and return any changes made."""
    loop = LearningLoop()
    loop.initialize_params()
    return loop.analyze_and_adjust(days)


def record_click(tracking_token: str) -> Optional[str]:
    """Record a click and return the alert_id."""
    tracker = OutcomeTracker()
    return tracker.record_click(tracking_token)
