-- Create Tables

-- Table to store different strategies
CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- Table to store different tickers
CREATE TABLE IF NOT EXISTS tickers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- Table to store different time frames for each ticker
CREATE TABLE IF NOT EXISTS ticker_time_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker_id INTEGER,
    duration TEXT NOT NULL,  -- This will store the actual time duration like '5', '15', '1h', etc.
    FOREIGN KEY (ticker_id) REFERENCES tickers (id)
);

-- Table to store stages for each strategy
CREATE TABLE IF NOT EXISTS strategy_stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER,
    description TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    FOREIGN KEY (strategy_id) REFERENCES strategies (id)
);

-- Table to store status for each ticker, time frame, and strategy combination at each stage
CREATE TABLE IF NOT EXISTS ticker_time_frame_strategy_status (
    ticker_id INTEGER,
    time_frame_id INTEGER,
    strategy_stage_id INTEGER,
    status TEXT DEFAULT 'waiting',
    PRIMARY KEY (ticker_id, time_frame_id, strategy_stage_id),
    FOREIGN KEY (ticker_id) REFERENCES tickers (id),
    FOREIGN KEY (strategy_stage_id) REFERENCES strategy_stages (id)
);

-- Table to store raw data from MongoDB for each ticker and time frame
CREATE TABLE IF NOT EXISTS ticker_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker_id INTEGER,
    time_frame_id INTEGER,
    tv_time TIMESTAMP,
    type TEXT,
    lt_blue_wave REAL,
    blue_wave REAL,
    vwap REAL,
    mny_flow REAL,
    buy INTEGER,
    blue_wave_crossing_up REAL,
    blue_wave_crossing_down REAL,
    zero INTEGER,
    hundred_percent INTEGER,
    ob_1_solid INTEGER,
    os_1_solid INTEGER,
    trigger_1 INTEGER,
    trigger_2 INTEGER,
    rsi REAL,
    sto_rsi REAL,
    FOREIGN KEY (ticker_id) REFERENCES tickers (id)
);

-- Table to store errors
CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker_id INTEGER,
    strategy_id INTEGER,
    error_message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticker_id) REFERENCES tickers (id),
    FOREIGN KEY (strategy_id) REFERENCES strategies (id)
);

-- Table to store alerts
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    strategy TEXT NOT NULL,
    stage TEXT NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Insert initial data

-- Inserting the 'MTBT' strategy
INSERT OR IGNORE INTO strategies (name) VALUES ('MTBT');

-- Inserting stages for 'MTBT' strategy
INSERT OR IGNORE INTO strategy_stages (strategy_id, description, sequence) VALUES 
    ((SELECT id FROM strategies WHERE name = 'MTBT'), 'Big Green Dot', 1),
    ((SELECT id FROM strategies WHERE name = 'MTBT'), 'Red Dot', 2),
    ((SELECT id FROM strategies WHERE name = 'MTBT'), 'Green Dot', 3);

-- Inserting tickers
INSERT OR IGNORE INTO tickers (name) VALUES 
    ('ETHUSD'), 
    ('BTCUSD'), 
    ('LINKUSD'), 
    ('MASKUSD'), 
    ('PEPEUSD'), 
    ('AVAXUSD'), 
    ('FTMUSD'), 
    ('AGIXUSD');
