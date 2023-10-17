import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from dateutil.parser import parse
import sqlite3
import logging
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
#from flask_socketio import emit, send, SocketIO
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from strategies import PatternStrategy
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logging.basicConfig(level=logging.DEBUG)

load_dotenv(dotenv_path="./.env")

MONGO_USERNAME = os.getenv("MONGO_USERNAME")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_IP = os.getenv("MONGO_IP")
MONGO_PORT = "27017"
MONGO_URI = f"mongodb://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_IP}:{MONGO_PORT}/?authMechanism=DEFAULT"
MONGO_DATABASE = "market_data"
MONGO_COLLECTION_MCB = "market_cipher_b"
MONGO_COLLECTION_TRADES = "trades"

mongo_client = MongoClient(MONGO_URI)
print(MONGO_URI)
db = mongo_client[MONGO_DATABASE]
collection = db[MONGO_COLLECTION_MCB]
trades_collection = db[MONGO_COLLECTION_TRADES]

# Directory of the script or current file.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DATABASE = os.path.join(DATA_DIR, 'database.db')
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
# app.secret_key = 'asdfasdf332fsdfawefsadf2f3daf'
# socketio = SocketIO(app, cors_allowed_origins="*")


def query_db(query, args=(), one=False):
    """Utility function to query the SQLite3 database."""
    with sqlite3.connect(DATABASE) as con:
        cur = con.cursor()
        result = cur.execute(query, args).fetchall()
        cur.close()
        return (result[0] if result else None) if one else result


class FileChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path == './tickers.txt':
            print("tickers.txt has been modified, updating tickers...")
            # This will re-read the tickers from the file.
            get_all_tickers_from_file()
        elif event.src_path == './dot_tickers.txt':
            print("dot_tickers.txt has been modified, updating dot tickers...")
            # This will re-read the dot tickers from the file.
            get_all_dot_tickers_from_file()


observer = Observer()
observer.schedule(FileChangeHandler(), path='.', recursive=False)
observer.start()


@app.route('/')
def index():
    # Retrieve tickers/plans from the database
    plans = get_all_plans_from_db()

    results = {}
    money_flows = {}  # Initialize money_flows here

    # Process each ticker/plan
    for plan in plans:
        strategy_instance = PatternStrategy(plan)
        strategy_result = strategy_instance.analyze()

        dots = {}
        if isinstance(strategy_result, dict):
            if strategy_result.get('first_big_green_dot_time'):
                dots['first_big_green_dot_time'] = strategy_result['first_big_green_dot_time']
            if strategy_result.get('red_dot_time'):
                dots['red_dot_time'] = True
            if strategy_result.get('breakout_time'):
                dots['green_dot_time'] = True

        # Organize results based on ticker_symbol then time_frame
        ticker = plan['ticker_symbol']
        time_frame = plan['time_frame']

        if ticker not in results:
            results[ticker] = {}
        results[ticker][time_frame] = dots

        # Fetch the most recent "Mny Flow" for each ticker and time frame
        current_record = collection.find_one(
            {"Time Frame": time_frame, "ticker": ticker}, sort=[('TV Time', -1)])
        if current_record and 'Mny Flow' in current_record:
            if ticker not in money_flows:
                money_flows[ticker] = {}
            money_flows[ticker][time_frame] = {
                'money_flow': current_record['Mny Flow']}

    return render_template('index.html', data=results, money_flow=money_flows)


@app.route('/trades')
def trades():
    # Fetch the last 5 trades for each ticker from the trades collection
    tickers = trades_collection.distinct("Ticker")
    trades_data = []

    for ticker in tickers:
        trades_for_ticker = list(trades_collection.find({'Ticker': ticker}).sort([('TV Time', -1)]).limit(10))
        trades_data.extend(trades_for_ticker)

    return render_template('trades.html', trades=trades_data)

@app.route('/dots')
def dots():
    try:
        # 1. Get the tickers from dot_tickers.txt file using the function
        dot_tickers = get_all_dot_tickers_from_file()
        print("Read tickers from dot_tickers.txt:", dot_tickers)

        results = []

        # 2. Query MongoDB for each ticker and timeframe
        for ticker, time_frame in dot_tickers:
            # Find the most recent record with a non-null Blue Wave Crossing UP or Down
            record = collection.find_one(
                {"Time Frame": time_frame, "ticker": ticker, "$or": [{"Blue Wave Crossing UP": {"$ne": "null"}}, {"Blue Wave Crossing Down": {"$ne": "null"}}]},
                sort=[('TV Time', -1)]
            )

            print("record for", ticker, time_frame, ":", record)

            if not record:
                continue

            if record['Blue Wave Crossing UP'] != "null":
                dot_color = 'green'
            else:  # If UP is null, then DOWN should be not-null
                dot_color = 'red'

            results.append((ticker, time_frame, dot_color))

        # Convert results to a nested dictionary for easy use in the template
        grouped_results = {}
        for ticker, time_frame, dot_color in results:
            if ticker not in grouped_results:
                grouped_results[ticker] = {}
            grouped_results[ticker][time_frame] = dot_color

        # 3. Render the dots.html template
        return render_template('dots.html', grouped_results=grouped_results)

    except Exception as e:
        # Handle errors and perhaps return a message to the user or log the error
        print(f"An error occurred: {e}")
        return render_template('error.html', error_message=str(e))


def process_log_entry(log_entry):
    """
    Processes a log entry and extracts relevant information.
    """
    result = {}

    # Check if the log entry is of interest
    if "Big Green Dot" in log_entry:
        # Extracting relevant details
        result['ticker'] = log_entry.get('ticker', None)
        result['time_frame'] = log_entry.get('Time Frame', None)

        # If the Big Green Dot is found for the first time, add the TV Time
        if not result.get('first_big_green_dot_time'):
            result['first_big_green_dot_time'] = log_entry.get('TV Time', None)
    return result


def get_all_tickers_from_file():
    plans = []
    with open('tickers.txt', 'r') as f:
        for line in f.readlines():
            ticker, time_frame = line.strip().split(', ')
            plans.append({"ticker_symbol": ticker, "time_frame": time_frame})
    return plans

def get_all_dot_tickers_from_file():
    dot_tickers = []
    with open('dot_tickers.txt', 'r') as f:
        for line in f.readlines():
            ticker, time_frame = line.strip().split(', ')
            dot_tickers.append((ticker, time_frame))
    return dot_tickers


def get_all_plans_from_db():
    return get_all_tickers_from_file()


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        ticker_symbol = request.form.get('ticker_symbol')
        time_frame = request.form.get('time_frame')

        # Insert or update the ticker in the tickers table
        ticker_id = insert_or_get_ticker(ticker_symbol)

        # Insert the time frame for the ticker
        insert_time_frame_for_ticker(ticker_id, time_frame)

        return redirect(url_for('index'))

    return render_template('settings.html')


@app.route('/clear_data', methods=['POST'])
def clear_data():
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()

            # Delete data from the 'tickers' table
            cursor.execute("DELETE FROM tickers")

            # Delete data from the 'ticker_time_frames' table
            cursor.execute("DELETE FROM ticker_time_frames")

            conn.commit()
            flash("Data cleared successfully", "success")
    except Exception as e:
        flash(f"Failed to clear data: {str(e)}", "error")

    return redirect(url_for('settings'))


def insert_or_get_ticker(ticker):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT OR IGNORE INTO tickers (name) VALUES (?)", (ticker,))
    cursor.execute("SELECT id FROM tickers WHERE name = ?", (ticker,))
    ticker_id = cursor.fetchone()[0]

    conn.commit()
    conn.close()

    return ticker_id


def insert_time_frame_for_ticker(ticker_id, time_frame):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT OR IGNORE INTO ticker_time_frames (ticker_id, duration) VALUES (?, ?)", (ticker_id, time_frame))

    conn.commit()
    conn.close()


def setup_database():
    logging.info("Setting up database...")
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        with open('schema.sql', 'r') as f:
            cursor.executescript(f.read())
        conn.commit()
        logging.info("Database setup completed successfully.")
    except Exception as e:
        logging.error(f"Error setting up database: {e}")
    finally:
        if conn:
            conn.close()


def setup_mongodb():
    logging.info("Setting up MongoDB...")
    try:
        mongo_client = MongoClient(MONGO_URI)
        db = mongo_client[MONGO_DATABASE]
        if MONGO_COLLECTION_MCB not in db.list_collection_names():
            db.create_collection(MONGO_COLLECTION_MCB)
            logging.info(f"Collection {MONGO_COLLECTION_MCB} created.")
        else:
            logging.info(f"Collection {MONGO_COLLECTION_MCB} already exists.")
        logging.info("MongoDB setup completed successfully.")
    except Exception as e:
        logging.error(f"Error setting up MongoDB: {e}")


setup_database()
setup_mongodb()

# if __name__ == "__main__":
#     socketio.run(app, host='0.0.0.0', debug=False, port=5000)
if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=False, port=5000)

