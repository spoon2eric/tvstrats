from collections import OrderedDict
import os
from dotenv import load_dotenv
from datetime import datetime
from dateutil.parser import parse
import logging
from flask import Flask, render_template
from flask_caching import Cache
from pymongo import MongoClient, DESCENDING
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logging.basicConfig(level=logging.DEBUG)

load_dotenv(dotenv_path="./.env")

MONGO_USERNAME = os.getenv("MONGO_USERNAME")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_IP = os.getenv("MONGO_IP")
MONGO_PORT = os.getenv("MONGO_PORT")
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


app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})
# Set default cache timeout to 5 minutes
app.config['CACHE_DEFAULT_TIMEOUT'] = 300

##########


class MongoConnection:
    def __init__(self, db_name):
        self.MONGO_URI = f"mongodb://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_IP}:{MONGO_PORT}/?authMechanism=DEFAULT"
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


@app.template_filter('format_datetime')
def format_datetime(value, format="%m-%d %H:%M"):
    if value is None or value == 'Undefined':
        return ""  # Return an empty string when the value is undefined or 'Undefined'
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime(format)

app.jinja_env.filters['format_datetime'] = format_datetime


@app.route('/')
@cache.cached(timeout=250)
def show_ui_collection():
    with MongoClient(MONGO_URI) as mongo_client:
        db = mongo_client[MONGO_DATABASE]
        ui_collection = db[MONGO_COLLECTION_UI]

        records = ui_collection.find({})
        grouped_records = {}
        for record in records:
            # Convert ObjectId to string
            record['_id'] = str(record['_id'])

            # Check if 'ticker' key exists in the record
            if 'ticker' in record:
                ticker = record['ticker']

                # Ensure the ticker key exists in the dictionary
                if ticker not in grouped_records:
                    grouped_records[ticker] = {'records': [], 'price': None}

                # Append the record to the ticker's record list
                grouped_records[ticker]['records'].append(record)

                # Check if the current record has a newer price and update accordingly
                if 'price' in record and (grouped_records[ticker]['price'] is None or record['last_updated'] > grouped_records[ticker]['records'][-1]['last_updated']):
                    # Format price to two decimal places before storing it
                    try:
                        grouped_records[ticker]['price'] = "{:.2f}".format(float(record['price']))
                    except ValueError:
                        # Handle the case where the price is not a valid number
                        grouped_records[ticker]['price'] = "N/A"
            else:
                # Handle the case where 'ticker' key is missing in the record
                print(f"'ticker' key not found in record: {record}")

    # Sort the grouped records by ticker keys
    sorted_grouped_records = dict(sorted(grouped_records.items()))

    # Pass the sorted records to the 'index.html' template
    return render_template('index.html', grouped_records=sorted_grouped_records)



@app.route('/trades')
@cache.cached(timeout=250)  # Cache this route
def trades():
    # Fetch the distinct tickers and sort them alphabetically
    tickers = sorted(trades_collection.distinct("Ticker"))

    trades_data = []
    for ticker in tickers:
        # Fetch the last 5 trades for this ticker
        trades_for_ticker = list(trades_collection.find(
            {'Ticker': ticker}).sort([('TV Time', -1)]).limit(5))
        # Add a tuple of ticker and its trades to the list
        trades_data.append((ticker, trades_for_ticker))

    # Sort trades_data based on the ticker (which is the first item of each tuple)
    trades_data.sort(key=lambda x: x[0])

    # If you need to pass it to the template as a dictionary, you can convert it
    trades_dict = {ticker: trades for ticker, trades in trades_data}

    return render_template('trades.html', trades=trades_dict)

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
                    dot_color = 'green' if record.get('is_green_dot') == "TRUE" else 'red' if record.get(
                        'is_red_dot') == "TRUE" else 'grey'

                    # Structure to hold ticker information
                    if ticker not in grouped_results:
                        grouped_results[ticker] = {}
                    grouped_results[ticker][time_frame] = dot_color

                    # Add money flow if it exists in the record
                    if 'money_flow' in record:
                        if ticker not in money_flows:
                            money_flows[ticker] = {}
                        money_flows[ticker][time_frame] = record['money_flow']

        # Sort grouped_results by tickers alphabetically
        sorted_grouped_results = OrderedDict(sorted(grouped_results.items()))

        # Render the dots.html template with the sorted tickers
        return render_template('dots.html', grouped_results=sorted_grouped_results, money_flow=money_flows)

    except Exception as e:
        print(f"An error occurred: {e}")
        return render_template('error.html', error_message=str(e))


@app.route('/ml-ai')
def show_ml_ai_alerts():
    with MongoClient(MONGO_URI) as mongo_client:
        db = mongo_client[MONGO_DATABASE]
        ml_alerts_collection = db['ml_alerts']

        ml_alerts = ml_alerts_collection.find({})

        # Group alerts based on Ticker and Time Frame
        grouped_alerts = {}
        for alert in ml_alerts:
            ticker = alert['Ticker']
            time_frame = alert['Time Frame']
            if ticker not in grouped_alerts:
                grouped_alerts[ticker] = {}
            if time_frame not in grouped_alerts[ticker]:
                grouped_alerts[ticker][time_frame] = []
            grouped_alerts[ticker][time_frame].append(alert)

        return render_template('ml-ai.html', grouped_alerts=grouped_alerts)


@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error_message=str(error)), 500


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


logging.info("tvstrats, version: v0.9.15")

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=False, port=5000)
