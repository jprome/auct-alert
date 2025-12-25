# Auction Alerts - 14-Day Minimum Value Loop

A system that turns messy fragmented auction data into actionable alerts, focused on estate/furniture auctions in Florida.

## 🎯 What This Does

1. **Scrapes** 3 auction sources (EstateSales.net, HiBid, Florida Surplus)
2. **Normalizes** data into a canonical schema
3. **Matches** items against your intent (e.g., dining tables under $1200 within 100 miles)
4. **Alerts** you via email when matches are found
5. **Tracks** outcomes (clicked/ignored)
6. **Learns** by adjusting parameters based on your engagement

## 📁 Project Structure

```
auction_alerts/
├── __init__.py           # Package init
├── config.py             # Configuration management
├── models.py             # Data models (AuctionItem, UserIntent, Alert)
├── db.py                 # Supabase database integration
├── normalization.py      # Raw data → canonical schema
├── intent_matching.py    # Match items against intents
├── alerts.py             # Email alert sending
├── outcomes.py           # Outcome tracking & learning loop
├── pipeline.py           # Main orchestration
├── scheduler.py          # APScheduler for automated runs
├── tracking_server.py    # Flask server for click tracking
└── sources/
    ├── __init__.py
    ├── base.py           # Base scraper class
    ├── estatesales.py    # EstateSales.net scraper
    ├── hibid.py          # HiBid.com scraper
    └── florida_surplus.py # Government surplus scraper
```

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.11+
- A Supabase account (free tier works)
- Gmail account (for sending alerts) or SendGrid API key

### 2. Setup Supabase

1. Create a new project at [supabase.com](https://supabase.com)
2. Go to SQL Editor and run the contents of `setup_supabase.sql`
3. Go to Settings → API and copy your:
   - Project URL
   - Service role key (not the anon key!)

### 3. Configure Environment

```bash
# Clone and enter directory
cd Auction

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and edit environment variables
cp .env.example .env
# Edit .env with your Supabase and email credentials
```

### 4. Initialize the System

```bash
# Set up a test user with your email
python -m auction_alerts.pipeline --setup your-email@example.com
```

### 5. Run the Pipeline

```bash
# Run once manually
python -m auction_alerts.pipeline --run

# Or start the scheduler (runs every 4 hours)
python -m auction_alerts.scheduler --mode schedule
```

## 📧 Email Setup

### Option 1: Gmail (Easy)

1. Enable 2-factor authentication on your Gmail
2. Create an App Password: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. In `.env`:
   ```
   EMAIL_PROVIDER=smtp
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASSWORD=your-16-char-app-password
   ```

### Option 2: SendGrid (Production)

1. Sign up at [sendgrid.com](https://sendgrid.com)
2. Create an API key
3. In `.env`:
   ```
   EMAIL_PROVIDER=sendgrid
   SENDGRID_API_KEY=SG.your-api-key
   ```

## 🔧 Running Modes

```bash
# Full scheduler (continuous, runs every 4 hours)
python -m auction_alerts.scheduler --mode schedule

# Single pipeline run
python -m auction_alerts.scheduler --mode once

# Update expired alerts only
python -m auction_alerts.scheduler --mode outcomes

# Run learning loop only
python -m auction_alerts.scheduler --mode learn
```

## 📊 Click Tracking (Optional)

To track when users click alert links:

```bash
# Start the tracking server
python -m auction_alerts.tracking_server --port 5000

# Set TRACKING_BASE_URL in .env
# TRACKING_BASE_URL=https://your-server.com
```

## 🧠 The Learning Loop

The system automatically adjusts parameters based on engagement:

| Click Rate | Action |
|------------|--------|
| < 20% | Increase confidence threshold (fewer, more relevant alerts) |
| 20-50% | No change (sweet spot) |
| > 50% | Decrease threshold (more alerts, might be missing good items) |

View changes:
```sql
SELECT * FROM learning_history ORDER BY changed_at DESC;
```

Revert a change:
```python
from auction_alerts.outcomes import LearningLoop
loop = LearningLoop()
loop.revert_last_change("confidence_threshold")
```

## 🔍 Monitoring

### Check Recent Alerts
```sql
SELECT alert_id, confidence_score, outcome, created_at 
FROM alerts 
ORDER BY created_at DESC 
LIMIT 20;
```

### Outcome Statistics
```sql
SELECT 
    outcome, 
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as percentage
FROM alerts 
WHERE created_at > NOW() - INTERVAL '14 days'
GROUP BY outcome;
```

### Items Closing Soon
```sql
SELECT item_id, title, current_price, closing_at 
FROM items 
WHERE closing_at BETWEEN NOW() AND NOW() + INTERVAL '48 hours'
ORDER BY closing_at;
```

## 🎛️ Customizing the Intent

Edit the default intent in `pipeline.py`:

```python
def create_default_intent(confidence_threshold: float = 0.6) -> UserIntent:
    return UserIntent(
        # Change these to match what YOU're looking for
        category=ItemCategory.FURNITURE,
        subtype=ItemSubtype.DINING_TABLE,
        keywords=["dining", "table", "dining table"],
        max_price=1200.0,           # Your budget
        max_distance_miles=100.0,   # From Miami
        # ...
    )
```

Or insert directly into Supabase:
```sql
INSERT INTO intents (intent_id, user_id, user_email, category, subtype, keywords, max_price)
VALUES ('my_intent', 'my_user', 'me@example.com', 'furniture', 'sofa', '["sofa", "couch"]', 800);
```

## 🧪 Testing Without Real Scraping

The scrapers include test data generation when actual scraping fails. This lets you test the full pipeline flow even without network access.

## 📝 Adding New Sources

1. Create a new file in `sources/` (e.g., `craigslist.py`)
2. Inherit from `BaseScraper`
3. Implement `fetch_listings()` and `parse_listing()`
4. Add to `sources/__init__.py`
5. Call from `pipeline.py`

Example:
```python
from .base import BaseScraper
from ..models import AuctionSource

class CraigslistScraper(BaseScraper):
    source = AuctionSource.CRAIGSLIST  # Add to models.py enum
    
    def fetch_listings(self, **kwargs) -> list[dict]:
        # Your scraping logic
        pass
    
    def parse_listing(self, raw_data: str, url: str) -> list[dict]:
        # Your parsing logic
        pass
```

## ⚠️ Important Notes

1. **Rate Limiting**: Scrapers have a 2-second delay between requests. Be respectful of source websites.

2. **Test Data**: When scraping fails, test data is generated. This is intentional for development.

3. **Email Limits**: Gmail has sending limits (~500/day). For higher volume, use SendGrid.

4. **Supabase Limits**: Free tier has limits. Monitor your usage.

## 🐛 Troubleshooting

**No emails received?**
- Check spam folder
- Verify SMTP credentials
- Run with `--log-level DEBUG`

**No matches found?**
- Lower `confidence_threshold` in intent
- Expand `max_price` or `max_distance_miles`
- Check that items have `category=furniture` and `subtype=dining_table`

**Database errors?**
- Verify `SUPABASE_URL` and `SUPABASE_KEY` in `.env`
- Make sure you ran `setup_supabase.sql`

## 📄 License

MIT - Do whatever you want with it.

---

Built for the 14-day minimum value loop. Keep it simple, ship it, learn from real data.
