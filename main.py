import json
import os
import io
import sys
from dotenv import load_dotenv
from datetime import datetime, timedelta
from dateutil.parser import parse
import logging
from flask import Flask, render_template, jsonify
from flask_caching import Cache
from pymongo import MongoClient, DESCENDING
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from telegram_notifier import send_telegram_message

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
MONGO_COLLECTION_UI = "user_interface"

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DATABASE]
collection = db[MONGO_COLLECTION_MCB]
trades_collection = db[MONGO_COLLECTION_TRADES]
ui_collection = db[MONGO_COLLECTION_UI]

# Directory of the script or current file.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DATABASE = os.path.join(DATA_DIR, 'database.db')
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})
app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # Set default cache timeout to 5 minutes
# app.secret_key = 'asdfasdf332fsdfawefsadf2f3daf'
# socketio = SocketIO(app, cors_allowed_origins="*")

##########


class MongoConnection:
    def __init__(self, db_name):
        self.MONGO_URI = f"mongodb://spoon2eric:Mtu19355%24@192.168.79.50:27017/?authMechanism=DEFAULT"
        self.db_name = db_name

    def __enter__(self):
        self.client = MongoClient(self.MONGO_URI)
        return self.client[self.db_name]

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()


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

################################
# New route
@app.template_filter('format_datetime')
def format_datetime(value, format="%m-%d %H:%M"):
    if value is None:
        return ""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime(format)

app.jinja_env.filters['format_datetime'] = format_datetime

@app.route('/')
def show_ui_collection():
    with MongoClient(MONGO_URI) as mongo_client:
        db = mongo_client[MONGO_DATABASE]
        ui_collection = db[MONGO_COLLECTION_UI]

        records = ui_collection.find({})
        grouped_records = {}
        for record in records:
            # Convert ObjectId to string
            record['_id'] = str(record['_id'])

            ticker = record['ticker']
            if ticker not in grouped_records:
                grouped_records[ticker] = []
            grouped_records[ticker].append(record)

    # Pass the grouped records to the 'index.html' template
    return render_template('index.html', grouped_records=grouped_records)

@app.route('/orig')
@cache.cached(timeout=250)  # Cache this route
def index():
    money_flows = {}
    with MongoConnection("market_data") as db:
        raw_results, logs = analyze_data(db, "./tickers.txt")

        # Transform results to match the expected structure
        transformed_results = {}
        for (ticker, time_frame), stage in raw_results.items():

            # Check and set a default value for stage if it's None
            if stage is None:
                stage = -1  # Or any other suitable default value

            if ticker not in transformed_results:
                transformed_results[ticker] = {}
            big_green_dot_time = None
            if stage >= 1:
                big_green_dot_time = find_big_green_dot(
                    db['market_cipher_b'], ticker, time_frame)
            transformed_results[ticker][time_frame] = {
                'stage': stage,
                'first_big_green_dot_time': big_green_dot_time
            }

            # Fetch the most recent "Mny Flow" for each ticker and time frame
            current_record = db['market_cipher_b'].find_one(
                {"Time Frame": time_frame, "ticker": ticker}, sort=[('TV Time', -1)])
            if current_record and 'Mny Flow' in current_record:
                if ticker not in money_flows:
                    money_flows[ticker] = {}
                money_flows[ticker][time_frame] = {
                    'money_flow': current_record['Mny Flow']}

    #print(transformed_results)

    return render_template('index_orig.html', data=transformed_results, money_flow=money_flows)


# End of New route

def group_results_by_ticker(results):
    """
    Group the analysis results by ticker symbol.
    """
    grouped = {}
    for (ticker, time_frame), stage in results.items():
        if ticker not in grouped:
            grouped[ticker] = {}
        grouped[ticker][time_frame] = stage
    return grouped
################################


@app.route('/trades')
@cache.cached(timeout=250)  # Cache this route
def trades():
    # Fetch the last 5 trades for each ticker from the trades collection
    tickers = trades_collection.distinct("Ticker")
    trades_data = []

    for ticker in tickers:
        trades_for_ticker = list(trades_collection.find(
            {'Ticker': ticker}).sort([('TV Time', -1)]).limit(5))
        trades_data.extend(trades_for_ticker)

    return render_template('trades.html', trades=trades_data)

@app.route('/dots')
@cache.cached(timeout=250)  # Cache this route
def dots():
    try:
        # Get the tickers from dot_tickers.txt file using the function
        dot_tickers = get_all_dot_tickers_from_file()

        grouped_results = {}
        money_flows = {}

        # Query MongoDB for each ticker and time frame
        with MongoClient(MONGO_URI) as mongo_client:
            db = mongo_client[MONGO_DATABASE]
            ui_collection = db[MONGO_COLLECTION_UI]

            for ticker, time_frame in dot_tickers:
                record = ui_collection.find_one(
                    {"time_frame": time_frame, "ticker": ticker},
                    sort=[('last_updated', -1)]
                )

                if record:
                    dot_color = 'green' if record.get('is_green_dot') == "TRUE" else 'red' if record.get('is_red_dot') == "TRUE" else 'grey'
                    
                    # Structure to hold ticker information
                    if ticker not in grouped_results:
                        grouped_results[ticker] = {}
                    grouped_results[ticker][time_frame] = dot_color
                    
                    # Add money flow if it exists in the record
                    if 'money_flow' in record:
                        if ticker not in money_flows:
                            money_flows[ticker] = {}
                        money_flows[ticker][time_frame] = record['money_flow']

        # Render the dots.html template
        return render_template('dots.html', grouped_results=grouped_results, money_flow=money_flows)

    except Exception as e:
        print(f"An error occurred: {e}")
        return render_template('error.html', error_message=str(e))

# @app.route('/dots')
# @cache.cached(timeout=250)  # Cache this route
# def dots():
#     money_flows = {}
#     try:
#         # 1. Get the tickers from dot_tickers.txt file using the function
#         dot_tickers = get_all_dot_tickers_from_file()
#         #print("Read tickers from dot_tickers.txt:", dot_tickers)

#         results = []

#         # 2. Query MongoDB for each ticker and timeframe
#         for ticker, time_frame in dot_tickers:
#             # Find the most recent record with a non-null Blue Wave Crossing UP or Down
#             with MongoConnection("market_data") as db:
#                 record = db[MONGO_COLLECTION_MCB].find_one(
#                     {"Time Frame": time_frame, "ticker": ticker, "$or": [{"Blue Wave Crossing UP":
#                                                                           {"$ne": "null"}}, {"Blue Wave Crossing Down": {"$ne": "null"}}]},
#                     sort=[('TV Time', -1)]
#                 )

#                 if not record:
#                     continue

#                 if record['Blue Wave Crossing UP'] != "null":
#                     dot_color = 'green'
#                 else:  # If UP is null, then DOWN should be not-null
#                     dot_color = 'red'

#                 results.append((ticker, time_frame, dot_color))

#                 # Fetch the most recent "Mny Flow" for each ticker and time frame
#                 current_record = db['market_cipher_b'].find_one(
#                     {"Time Frame": time_frame, "ticker": ticker}, sort=[('TV Time', -1)])
#                 if current_record and 'Mny Flow' in current_record:
#                     if ticker not in money_flows:
#                         money_flows[ticker] = {}
#                     money_flows[ticker][time_frame] = {
#                         'money_flow': current_record['Mny Flow']}

#         # Convert results to a nested dictionary for easy use in the template
#         grouped_results = {}
#         for ticker, time_frame, dot_color in results:
#             if ticker not in grouped_results:
#                 grouped_results[ticker] = {}
#             grouped_results[ticker][time_frame] = dot_color

#         # 3. Render the dots.html template
#         return render_template('dots.html', grouped_results=grouped_results, money_flow=money_flows)

#     except Exception as e:
#         # Handle errors and perhaps return a message to the user or log the error
#         print(f"An error occurred: {e}")
#         return render_template('error.html', error_message=str(e))

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error_message=str(error)), 500


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


def setup_mongodb():
    logging.info("Setting up MongoDB...")
    try:
        with MongoConnection(MONGO_DATABASE) as db:
            if MONGO_COLLECTION_MCB not in db.list_collection_names():
                db.create_collection(MONGO_COLLECTION_MCB)
                logging.info(f"Collection {MONGO_COLLECTION_MCB} created.")
            else:
                logging.info(
                    f"Collection {MONGO_COLLECTION_MCB} already exists.")
            logging.info("MongoDB setup completed successfully.")
    except Exception as e:
        logging.error(f"Error setting up MongoDB: {e}")


################################
def read_config_file(path):
    with open(path, 'r') as f:
        lines = f.readlines()
        return [tuple(line.strip().split(', ')) for line in lines]


def analyze_sequence_from_big_green_dot(collection, ticker, time_frame):
    # Find the most recent big green dot
    start_time = find_big_green_dot(collection, ticker, time_frame)

    # If there's no big green dot, we can't proceed
    if not start_time:
        print(
            f"No Big Green Dot found for {ticker} in {time_frame} time frame.")
        return

    # Start the sequence analysis
    stage = analyze_dots_for_sequence(
        collection, start_time, ticker, time_frame)

    # If the sequence is broken, find the next big green dot and restart the sequence analysis
    while stage == -1:
        # Update the start_time to one second after the last processed time to avoid reprocessing the same data
        if start_time.endswith('Z'):
            start_time = start_time[:-1]
        updated_start_time = datetime.fromisoformat(
            start_time) + timedelta(seconds=1)

        # Convert back to string format
        updated_start_time_str = updated_start_time.isoformat() + "Z"

        start_time = find_big_green_dot(collection, ticker, time_frame)

        # If there's no new big green dot, exit the loop
        if not start_time or start_time <= updated_start_time_str:
            break

        stage = analyze_dots_for_sequence(
            collection, start_time, ticker, time_frame)

    return stage or -1


def find_big_green_dot(collection, ticker, time_frame):
    """
    Search for the most recent record with the specified ticker and time frame where "Buy" is "1".
    Extract "TV Time" from that record and return it.
    """
    record = collection.find_one({
        "ticker": ticker,
        "Time Frame": time_frame,
        "Buy": "1"
    }, sort=[("TV Time", DESCENDING)])
    # Debug statement
    #print(f"Record for {ticker} and {time_frame}: {record}")

    if record:
        log_dot('Big Green', record, stage=1)
        # Debug statement
        #print(
        #    f"Returning 'TV Time' for {ticker} and {time_frame}: {record['TV Time']}")
        return record["TV Time"]
    return None


def get_records_after_time(collection, start_time, ticker, time_frame):
    """
    Fetch records after the start_time for the specified ticker and time frame.
    Sort them in ascending order based on "TV Time".
    """
    records = collection.find({
        "TV Time": {"$gt": start_time},
        "ticker": ticker,
        "Time Frame": time_frame
    }).sort("TV Time", 1)

    return list(records)


# Create a global variable to store the logs
logs = []


def log_dot(dot_type, record, stage=None):
    """
    Log the found dot (either Red or Green) for debugging.
    """
    log_message = ""
    if stage:
        log_message = f"Stage {stage} completed: {dot_type} Dot for {record['ticker']} at {record['TV Time']} (Time Frame: {record['Time Frame']}) with value {record['Blue Wave Crossing UP' if dot_type == 'Green' else 'Blue Wave Crossing Down']}"
    else:
        log_message = f"{dot_type} Dot found for {record['ticker']} at {record['TV Time']} (Time Frame: {record['Time Frame']}) with value {record['Blue Wave Crossing UP' if dot_type == 'Green' else 'Blue Wave Crossing Down']}"

    logs.append(log_message)


def analyze_dots_for_sequence(collection, start_time, ticker, time_frame):
    stage = 1
    #logging.info(f"in stage start for {ticker}/{time_frame}: {stage}")
    last_red_dot_value = float('-inf')
    stage_2_red_dot_value = None
    #last_processed_record = None

    records = get_records_after_time(
        collection, start_time, ticker, time_frame)

    for record in records:
        if stage == 1:
            red_dot_value_str = record['Blue Wave Crossing Down']
            if red_dot_value_str is not None and red_dot_value_str != 'null':
                red_dot_value = float(red_dot_value_str)
                if red_dot_value >= 9:  # Change this value to find First Red Dot
                    stage = 2
                    #logging.info("Stage 2 set due to red_dot_value: %s", red_dot_value)
                    stage_2_red_dot_value = red_dot_value
                    log_dot('Red', record, stage=2)
                else:
                    log_dot('Red', record)
                if red_dot_value > last_red_dot_value and red_dot_value < 0:
                    last_red_dot_value = red_dot_value
                    #logging.info("Red dot value is <0: %s", red_dot_value)

        elif stage == 2:
            #logging.info(f"Stage 2 for {ticker}/{time_frame}: {stage}")
            #logging.info(f"#### Stage 2 record: {record}")
            red_dot_value_str = record['Blue Wave Crossing Down']
            green_dot_value_str = record['Blue Wave Crossing UP']

            if red_dot_value_str is not None and red_dot_value_str != 'null':
                red_dot_value = float(red_dot_value_str)
                if red_dot_value > stage_2_red_dot_value:
                    #logging.info("red_dot_value: {red_dot_value}, stage_2_red_dot_value: {stage_2_red_dot_value}")
                    print(
                        f"Breaking sequence: Found Red Dot for {record['ticker']} at {record['TV Time']} (Time Frame: {record['Time Frame']}) with value {red_dot_value} which is higher than Stage 2 Red Dot value.")
                    stage = -1  # Indicate a broken sequence
                    #logging.info("Breaking out of stage")
                    break

            if green_dot_value_str is not None and green_dot_value_str != 'null':
                green_dot_value = float(green_dot_value_str)
                if green_dot_value <= -9: #Change value for Stage 3 green dot
                    stage = 3
                    #logging.info("Green Dot value <= -9, setting to Stage 3.")
                    log_dot('Green', record, stage=3)

                    # Insert/update the trade record after detecting Stage 3
                    unique_criteria = {
                        "Time Frame": time_frame,
                        "TV Time": record['TV Time'],
                        "Ticker": ticker
                    }
                    update_data = {
                        "$setOnInsert": {
                            "Trade": "Buy",
                            "Message": 0
                        }
                    }
                    with MongoConnection("market_data") as db:
                        db['trades'].update_one(unique_criteria, update_data, upsert=True)

                        # Check if the message for this trade has been sent already
                        trade_record = db['trades'].find_one(unique_criteria)
                        if trade_record and trade_record.get("Message") == 0:
                            try:
                                # Notify Telegram
                                message = f"Trade Alert! Buy for {ticker} at {record['TV Time']} (Time Frame: {time_frame})"
                                send_telegram_message(message)

                                # Update the Message flag to 1
                                db['trades'].update_one(unique_criteria, {"$set": {"Message": 1}})
                            except Exception as e:
                                print(f"In main, Failed to send Telegram message. Error: {e}")  # Print to console
                                logging.error(f"Failed to send Telegram message. Error: {e}")

                    #break
                else:
                    log_dot('Green', record)

        elif stage == 3:
            #logging.info(f"Stage 3 for {ticker}/{time_frame}: {stage} with {record}")
            # Transition to stage 4 after processing stage 3
            stage_3_tv_time_str = record['TV Time']
            stage_3_tv_time = datetime.strptime(stage_3_tv_time_str, "%Y-%m-%dT%H:%M:%SZ")
            stage_4_start_time = stage_3_tv_time + timedelta(seconds=1)
            stage = 4
            # Continue to the next iteration, or handle other logic as needed

        elif stage == 4:
            #logging.info(f"Stage 4 for {ticker}/{time_frame}: {stage} with {record}")
            current_tv_time_str = record['TV Time']
            current_tv_time = datetime.strptime(current_tv_time_str, "%Y-%m-%dT%H:%M:%SZ")
            red_dot_value_str = record['Blue Wave Crossing Down']

            if current_tv_time >= stage_4_start_time:
                if red_dot_value_str is not None and red_dot_value_str != 'null':
                    red_dot_value = float(red_dot_value_str)
                    #logging.info(f"Stage 4: Found Red Dot for {record['ticker']} at {record['TV Time']} (Time Frame: {record['Time Frame']}) with value {red_dot_value}. Transitioning to stage -1.")
                    stage = -1  # Indicate a broken sequence
                    # If you are in a loop, use 'continue' or 'break' depending on your logic
                    # If this is a function, 'return stage' would be appropriate
                else:
                    continue
                    #logging.info(f"Stage 4: No Red Dot found for {record['ticker']} at {record['TV Time']} (Time Frame: {record['Time Frame']}). Continuing...")

    return stage


def analyze_data(db, config_file_path):
    # Redirect the standard output to a StringIO object to capture the logs
    old_stdout = sys.stdout
    new_stdout = io.StringIO()
    sys.stdout = new_stdout

    ticker_time_pairs = read_config_file(config_file_path)

    results = {}
    for ticker, time_frame in ticker_time_pairs:
        stage = analyze_sequence_from_big_green_dot(
            db['market_cipher_b'], ticker, time_frame)
        results[(ticker, time_frame)] = stage

    # Reset the standard output
    sys.stdout = old_stdout

    # Return the results and the captured logs
    return results, new_stdout.getvalue().splitlines()

COINMARKETCAP_API_KEY = os.getenv("COINMARKET_API_KEY")

@app.route('/price/<string:ticker_name>', methods=['GET'])
@cache.cached(timeout=600)  # Cache this route for 10 minutes
def get_ticker_price(ticker_name):
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
    parameters = {
        'symbol': ticker_name,
        'convert': 'USD'
    }
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': COINMARKETCAP_API_KEY,
    }

    session = requests.Session()
    session.headers.update(headers)

    try:
        response = session.get(url, params=parameters)
        data = json.loads(response.text)
        if 'data' in data and ticker_name in data['data'] and 'quote' in data['data'][ticker_name] and 'USD' in data['data'][ticker_name]['quote'] and 'price' in data['data'][ticker_name]['quote']['USD']:
            price = data['data'][ticker_name]['quote']['USD']['price']
            return jsonify({'price': price})
        else:
            return jsonify({'error': 'Price data not available for the requested ticker'}), 404
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.TooManyRedirects) as e:
        print(e)
        return jsonify({'error': 'Failed to fetch ticker price'}), 500


setup_mongodb()
logging.info("tvstrats, version: v0.9.9")

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=False, port=5000)
