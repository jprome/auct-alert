-- =============================================================================
-- Supabase Schema for Auction Alerts
-- =============================================================================
-- 
-- Run this SQL in your Supabase SQL Editor to create all required tables.
-- Dashboard: https://app.supabase.com → Your Project → SQL Editor
--
-- Tables:
-- 1. raw_data - Stores raw HTML/JSON from scrapers
-- 2. items - Normalized auction items
-- 3. users - Users who receive alerts
-- 4. intents - User search intents/preferences
-- 5. alerts - Sent alerts with outcome tracking
-- 6. learning_params - Adjustable parameters for learning loop
-- 7. learning_history - History of parameter changes
-- =============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- 1. RAW_DATA TABLE
-- Stores raw HTML/JSON from each scraper run
-- =============================================================================
CREATE TABLE IF NOT EXISTS raw_data (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    content TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'html', -- 'html' or 'json'
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for querying by source and time
CREATE INDEX IF NOT EXISTS idx_raw_data_source ON raw_data(source);
CREATE INDEX IF NOT EXISTS idx_raw_data_scraped_at ON raw_data(scraped_at);

-- =============================================================================
-- 2. ITEMS TABLE
-- Normalized auction items from all sources
-- =============================================================================
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL DEFAULT 'other',
    subtype TEXT DEFAULT 'other',
    current_price DECIMAL(10, 2),
    starting_price DECIMAL(10, 2),
    buy_now_price DECIMAL(10, 2),
    closing_at TIMESTAMPTZ,
    pickup_location JSONB, -- {city, state, lat, lng}
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_data_id UUID REFERENCES raw_data(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_items_source ON items(source);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_closing_at ON items(closing_at);
CREATE INDEX IF NOT EXISTS idx_items_current_price ON items(current_price);

-- =============================================================================
-- 3. USERS TABLE
-- Users who receive alerts
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- 4. INTENTS TABLE
-- User search intents/preferences
-- =============================================================================
CREATE TABLE IF NOT EXISTS intents (
    intent_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    user_email TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'furniture',
    subtype TEXT,
    keywords JSONB DEFAULT '[]', -- array of keywords
    max_price DECIMAL(10, 2) NOT NULL DEFAULT 1200,
    max_distance_miles DECIMAL(10, 2) NOT NULL DEFAULT 100,
    reference_lat DECIMAL(10, 6) NOT NULL DEFAULT 25.7617, -- Miami
    reference_lng DECIMAL(10, 6) NOT NULL DEFAULT -80.1918,
    min_hours_before_close INTEGER NOT NULL DEFAULT 2,
    max_hours_before_close INTEGER NOT NULL DEFAULT 48,
    confidence_threshold DECIMAL(3, 2) NOT NULL DEFAULT 0.6,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_intents_user_id ON intents(user_id);
CREATE INDEX IF NOT EXISTS idx_intents_is_active ON intents(is_active);

-- =============================================================================
-- 5. ALERTS TABLE
-- Sent alerts with outcome tracking
-- =============================================================================
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES items(item_id),
    intent_id TEXT NOT NULL REFERENCES intents(intent_id),
    user_id TEXT NOT NULL REFERENCES users(id),
    confidence_score DECIMAL(3, 2) NOT NULL,
    match_reasons JSONB DEFAULT '[]', -- array of reason strings
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    clicked_at TIMESTAMPTZ,
    outcome TEXT NOT NULL DEFAULT 'pending', -- pending, clicked, ignored, expired, won, lost
    outcome_updated_at TIMESTAMPTZ,
    tracking_token TEXT UNIQUE NOT NULL
);

-- Indexes for outcome tracking
CREATE INDEX IF NOT EXISTS idx_alerts_item_id ON alerts(item_id);
CREATE INDEX IF NOT EXISTS idx_alerts_intent_id ON alerts(intent_id);
CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_outcome ON alerts(outcome);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_tracking_token ON alerts(tracking_token);

-- =============================================================================
-- 6. LEARNING_PARAMS TABLE
-- Adjustable parameters for the learning loop
-- =============================================================================
CREATE TABLE IF NOT EXISTS learning_params (
    param_name TEXT PRIMARY KEY,
    current_value DECIMAL(10, 4) NOT NULL,
    previous_value DECIMAL(10, 4),
    change_reason TEXT,
    changed_at TIMESTAMPTZ,
    min_value DECIMAL(10, 4) NOT NULL DEFAULT 0,
    max_value DECIMAL(10, 4) NOT NULL DEFAULT 999999,
    step_size DECIMAL(10, 4) NOT NULL DEFAULT 0.1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- 7. LEARNING_HISTORY TABLE
-- History of parameter changes for reversibility
-- =============================================================================
CREATE TABLE IF NOT EXISTS learning_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    param_name TEXT NOT NULL REFERENCES learning_params(param_name),
    old_value DECIMAL(10, 4) NOT NULL,
    new_value DECIMAL(10, 4) NOT NULL,
    reason TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for history queries
CREATE INDEX IF NOT EXISTS idx_learning_history_param ON learning_history(param_name);
CREATE INDEX IF NOT EXISTS idx_learning_history_changed_at ON learning_history(changed_at);

-- =============================================================================
-- ROW LEVEL SECURITY (Optional but recommended)
-- =============================================================================
-- For the MVP, you can skip RLS since we're using the service role key.
-- In production, you would enable RLS and create policies.

-- ALTER TABLE users ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE intents ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- SAMPLE DATA: Insert a test user and intent
-- =============================================================================
-- Uncomment and modify the email to set up your test user

/*
INSERT INTO users (id, email, name) VALUES
    ('test_user_001', 'your-email@example.com', 'Test User')
ON CONFLICT (id) DO NOTHING;

INSERT INTO intents (
    intent_id, user_id, user_email, category, subtype, 
    keywords, max_price, max_distance_miles, confidence_threshold
) VALUES (
    'test_intent_001', 
    'test_user_001', 
    'your-email@example.com',
    'furniture',
    'dining_table',
    '["dining", "table", "dining table"]',
    1200,
    100,
    0.6
) ON CONFLICT (intent_id) DO NOTHING;
*/

-- =============================================================================
-- USEFUL QUERIES
-- =============================================================================

-- View recent alerts with outcomes
-- SELECT alert_id, item_id, confidence_score, outcome, created_at 
-- FROM alerts ORDER BY created_at DESC LIMIT 20;

-- Get outcome statistics
-- SELECT outcome, COUNT(*) as count 
-- FROM alerts 
-- WHERE created_at > NOW() - INTERVAL '14 days'
-- GROUP BY outcome;

-- View parameter history
-- SELECT * FROM learning_history ORDER BY changed_at DESC LIMIT 10;

-- Find items closing soon
-- SELECT item_id, title, current_price, closing_at 
-- FROM items 
-- WHERE closing_at BETWEEN NOW() AND NOW() + INTERVAL '48 hours'
-- ORDER BY closing_at;
