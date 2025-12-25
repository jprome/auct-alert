"""
Alert Sending module for Auction Alerts.

Handles sending email alerts to users when matching items are found.
Supports both SMTP and SendGrid for email delivery.
"""

import uuid
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional

from .config import get_email_config, get_app_config
from .db import get_db
from .models import Alert, AlertOutcome, AuctionItem, UserIntent
from .intent_matching import MatchResult

logger = logging.getLogger(__name__)


# =============================================================================
# EMAIL TEMPLATES
# =============================================================================

ALERT_EMAIL_SUBJECT = "🔔 Auction Alert: {title}"

ALERT_EMAIL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #2c5282; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; background: #f7fafc; }}
        .item-card {{ background: white; border-radius: 8px; padding: 20px; margin: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .price {{ font-size: 24px; font-weight: bold; color: #2b6cb0; }}
        .details {{ margin: 10px 0; }}
        .detail-row {{ display: flex; margin: 5px 0; }}
        .detail-label {{ font-weight: bold; width: 120px; }}
        .cta-button {{ display: inline-block; background: #38a169; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-weight: bold; margin: 15px 0; }}
        .cta-button:hover {{ background: #2f855a; }}
        .confidence {{ background: #edf2f7; padding: 10px; border-radius: 4px; margin: 10px 0; }}
        .footer {{ text-align: center; padding: 20px; color: #718096; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔔 Auction Alert</h1>
        </div>
        <div class="content">
            <div class="item-card">
                <h2>{title}</h2>
                <p class="price">{price_display}</p>
                
                <div class="details">
                    <div class="detail-row">
                        <span class="detail-label">Source:</span>
                        <span>{source}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Location:</span>
                        <span>{location}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Closes:</span>
                        <span>{closing_time}</span>
                    </div>
                </div>
                
                <p>{description}</p>
                
                <div class="confidence">
                    <strong>Match Score:</strong> {confidence_score}%<br>
                    <small>{match_reasons}</small>
                </div>
                
                <a href="{tracking_url}" class="cta-button">View Auction →</a>
            </div>
        </div>
        <div class="footer">
            <p>You're receiving this because you set up alerts for furniture auctions in Florida.</p>
            <p>Auction Alerts - Your 14-Day Value Loop</p>
        </div>
    </div>
</body>
</html>
"""

ALERT_EMAIL_TEXT = """
AUCTION ALERT: {title}

Price: {price_display}
Source: {source}
Location: {location}
Closes: {closing_time}

{description}

Match Score: {confidence_score}%
Reasons: {match_reasons}

View auction: {tracking_url}

---
Auction Alerts - Your 14-Day Value Loop
"""


# =============================================================================
# ALERT SENDER CLASS
# =============================================================================

class AlertSender:
    """
    Sends email alerts for matching auction items.
    
    Usage:
        sender = AlertSender()
        sender.send_alerts(matches)
    """
    
    def __init__(self):
        """Initialize the alert sender."""
        self.email_config = get_email_config()
        self.app_config = get_app_config()
        self.db = get_db()
    
    def send_alerts(self, matches: list[MatchResult]) -> list[Alert]:
        """
        Send alerts for all matches.
        
        Args:
            matches: List of MatchResult objects
            
        Returns:
            List of Alert objects that were sent
        """
        sent_alerts = []
        
        for match in matches:
            # Check if we already alerted for this item-intent pair
            if self.db.check_alert_exists(match.item.item_id, match.intent.intent_id):
                logger.debug(f"Alert already exists for {match.item.item_id} / {match.intent.intent_id}")
                continue
            
            # Create and send alert
            alert = self._create_alert(match)
            
            try:
                self._send_email(match, alert)
                self.db.update_alert_sent(alert.alert_id)
                sent_alerts.append(alert)
                logger.info(f"Sent alert {alert.alert_id} for {match.item.title[:50]}")
            except Exception as e:
                logger.error(f"Failed to send alert {alert.alert_id}: {e}")
                continue
        
        logger.info(f"Sent {len(sent_alerts)}/{len(matches)} alerts")
        return sent_alerts
    
    def _create_alert(self, match: MatchResult) -> Alert:
        """Create an Alert record."""
        alert = Alert(
            alert_id=f"alert_{uuid.uuid4().hex[:12]}",
            item_id=match.item.item_id,
            intent_id=match.intent.intent_id,
            user_id=match.intent.user_id,
            confidence_score=match.confidence_score,
            match_reasons=match.match_reasons,
            tracking_token=uuid.uuid4().hex,
        )
        
        # Save to database
        self.db.create_alert(alert)
        
        return alert
    
    def _send_email(self, match: MatchResult, alert: Alert) -> None:
        """Send the alert email."""
        # Build email content
        item = match.item
        intent = match.intent
        
        # Format values for display
        price_display = f"${item.current_price:.0f}" if item.current_price else "Price not listed"
        location = item.pickup_location.city if item.pickup_location else "Florida"
        closing_time = item.closing_at.strftime("%B %d at %I:%M %p") if item.closing_at else "See listing"
        
        # Build tracking URL
        if self.app_config.tracking_base_url:
            tracking_url = f"{self.app_config.tracking_base_url}/click/{alert.tracking_token}"
        else:
            # Direct link if no tracking server
            tracking_url = item.source_url
        
        # Template variables
        template_vars = {
            "title": item.title,
            "price_display": price_display,
            "source": item.source.value.replace("_", " ").title(),
            "location": location,
            "closing_time": closing_time,
            "description": item.description[:300] + "..." if len(item.description) > 300 else item.description,
            "confidence_score": int(match.confidence_score * 100),
            "match_reasons": " • ".join(match.match_reasons),
            "tracking_url": tracking_url,
        }
        
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = ALERT_EMAIL_SUBJECT.format(**template_vars)
        msg["From"] = f"{self.email_config.from_name} <{self.email_config.from_email}>"
        msg["To"] = intent.user_email
        
        # Attach text and HTML versions
        text_content = ALERT_EMAIL_TEXT.format(**template_vars)
        html_content = ALERT_EMAIL_HTML.format(**template_vars)
        
        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))
        
        # Send based on provider
        if self.email_config.provider == "sendgrid":
            self._send_via_sendgrid(msg, intent.user_email)
        else:
            self._send_via_smtp(msg, intent.user_email)
    
    def _send_via_smtp(self, msg: MIMEMultipart, to_email: str) -> None:
        """Send email via SMTP."""
        with smtplib.SMTP(self.email_config.smtp_host, self.email_config.smtp_port) as server:
            server.starttls()
            if self.email_config.smtp_user and self.email_config.smtp_password:
                server.login(self.email_config.smtp_user, self.email_config.smtp_password)
            server.send_message(msg)
    
    def _send_via_sendgrid(self, msg: MIMEMultipart, to_email: str) -> None:
        """Send email via SendGrid API."""
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail, Email, To, Content
        except ImportError:
            logger.error("SendGrid package not installed. Run: pip install sendgrid")
            raise
        
        sg = sendgrid.SendGridAPIClient(api_key=self.email_config.sendgrid_api_key)
        
        # Extract content from MIMEMultipart
        html_content = None
        text_content = None
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                html_content = part.get_payload(decode=True).decode()
            elif part.get_content_type() == "text/plain":
                text_content = part.get_payload(decode=True).decode()
        
        message = Mail(
            from_email=Email(self.email_config.from_email, self.email_config.from_name),
            to_emails=To(to_email),
            subject=msg["Subject"],
            html_content=html_content or text_content,
        )
        
        response = sg.send(message)
        
        if response.status_code not in (200, 201, 202):
            raise Exception(f"SendGrid error: {response.status_code}")


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def send_alerts(matches: list[MatchResult]) -> list[Alert]:
    """
    Convenience function to send alerts.
    
    Args:
        matches: List of MatchResult objects
        
    Returns:
        List of sent Alert objects
    """
    sender = AlertSender()
    return sender.send_alerts(matches)


def create_test_alert(
    item: AuctionItem,
    intent: UserIntent,
    confidence: float = 0.8
) -> Alert:
    """
    Create a test alert (for development).
    
    Args:
        item: The auction item
        intent: The user intent
        confidence: Confidence score
        
    Returns:
        Alert object (not sent)
    """
    return Alert(
        alert_id=f"test_alert_{uuid.uuid4().hex[:8]}",
        item_id=item.item_id,
        intent_id=intent.intent_id,
        user_id=intent.user_id,
        confidence_score=confidence,
        match_reasons=["Test alert"],
        tracking_token=uuid.uuid4().hex,
    )
