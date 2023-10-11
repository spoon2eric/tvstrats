import collections
import sqlite3
from typing import Collection
from pymongo import MongoClient
import os
from dateutil.parser import parse
import logging

# MongoDB Configuration from provided main.py
MONGO_USERNAME = os.getenv("MONGO_USERNAME")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_IP = os.getenv("MONGO_IP")
MONGO_PORT = os.getenv("MONGO_PORT")
MONGO_URI = f"mongodb://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_IP}:{MONGO_PORT}/?authMechanism=DEFAULT"
MONGO_DATABASE = "market_data"
MONGO_COLLECTION_MCB = "market_cipher_b"

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DATABASE]
mongo_collection = mongo_db[MONGO_COLLECTION_MCB]

# SQLite Configuration from provided main.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DATABASE = os.path.join(DATA_DIR, 'database.db')

# Base Strategy Class


class Strategy:
    def __init__(self, plan):
        self.plan = plan

    def fetch_data(self):
        # Fetch data from MongoDB based on the plan's settings (ticker, time frame, etc.)
        pass

    def analyze(self):
        # Analyze fetched data and determine results
        pass

    def update_sqlite(self):
        # Update database.db to reflect changes in the UI
        pass

# MTBT Strategy (As an example)


class MTBTStrategy(Strategy):
    def fetch_data(self):
        # Implement data fetching specific to MTBT strategy
        pass

    def analyze(self):
        # Implement data analysis specific to MTBT strategy
        pass

    def update_sqlite(self):
        # Implement SQLite updates specific to MTBT strategy
        pass


class PatternStrategy(Strategy):
    def __init__(self, plan):
        super().__init__(plan)
        self.time_frame = plan['time_frame']
        self.ticker_symbol = plan['ticker_symbol']

    def analyze(self):
        return self.find_pattern_sequence()

    def find_pattern_sequence(self):
        time_frame = self.time_frame
        ticker_symbol = self.ticker_symbol
        # Add logging statements here to debug
        logging.debug(f"Time Frame: {time_frame}")
        logging.debug(f"Ticker Symbol: {ticker_symbol}")

        def find_next_dot(current_time, direction):
            """
            Find the next Red Dot or Green Dot after the provided time based on the direction.
            """
            logging.debug("Entering find_next_dot function")
            field = 'Blue Wave Crossing UP' if direction == 'up' else 'Blue Wave Crossing Down'
            parsed_time = parse(current_time)

            # Log the query parameters
            logging.debug(
                f"Query Parameters - field: {field}, TV Time: {parsed_time.isoformat()}, Time Frame: {time_frame}, ticker: {ticker_symbol}")

            count = mongo_collection.count_documents({
                field: {'$ne': "null"},
                'TV Time': {'$gt': parsed_time.isoformat()},
                "Time Frame": time_frame,
                "ticker": ticker_symbol
            })
            logging.debug(f"Number of Records Returned: {count}")

            # Redefine the cursor here:
            cursor = mongo_collection.find({
                field: {'$ne': "null"},
                'TV Time': {'$gt': parsed_time.isoformat()},
                "Time Frame": time_frame,
                "ticker": ticker_symbol
            }, sort=[('TV Time', 1)])
            for record in cursor:
                try:
                    value = float(record[field])
                    if direction == 'down':
                        if value > 0:  # Found a red dot with value > 0
                            logging.debug(
                                f"Found Red Dot at {record['TV Time']}: {record[field]}")
                            return record
                        else:
                            logging.debug(
                                f"Examined Red Dot (value <= 0) at {record['TV Time']}: {record[field]}")
                            continue
                    else:  # direction == 'up'
                        if 0 > value > -55:  # Green Dot with value < 0 but greater than -55
                            logging.debug(
                                f"Found Green Dot at {record['TV Time']}: {record[field]}")
                            return record
                        else:
                            logging.debug(
                                f"Examined Green Dot (value not within range) at {record['TV Time']}: {record[field]}")
                            continue
                except ValueError as e:
                    logging.debug(
                        f"Error parsing value at {record['TV Time']}: {e}")
                    continue

            # If no matching record is found, return None
            if direction == 'down':
                logging.debug(
                    "No suitable Red Dot found after considering all records.")
            else:
                logging.debug(
                    "No suitable Green Dot found after considering all records.")
            return None

        # Step 0: Find the latest Big Green Dot
        big_green_dot = mongo_collection.find_one(
            {"Time Frame": time_frame, "ticker": ticker_symbol, "Buy": "1"}, sort=[('TV Time', -1)])

        logging.debug(f"Big Green Dot found: {big_green_dot}")
        logging.debug(f"Big Green Dot Query Result: {big_green_dot}")

        if not big_green_dot:
            logging.debug("No Big Green Dot found.")
            return {
                "message": "No Big Green Dot found for " + ticker_symbol,
                "big_green_dot_time": None,
                "breakout_time": None
            }
        dots_found = {
            "big_green_dot_time": big_green_dot['TV Time'],
            "red_dot_time": None,
            "breakout_time": None
        }

        current_time = big_green_dot['TV Time']

        # Step 1: Search for the next Red Dot with value > 0
        red_dot = find_next_dot(current_time, 'down')
        if red_dot:
            dots_found["red_dot_time"] = red_dot['TV Time']
            current_time = red_dot['TV Time']

            # Step 2: Search for the next Green Dot
            green_dot = find_next_dot(current_time, 'up')
            if green_dot:
                dots_found["breakout_time"] = green_dot['TV Time']
            else:
                logging.debug(f"No Green Dot found after Red Dot.")
                return "No Green Dot found after Red Dot."

        # Step 3: Action or Alert
        if dots_found["red_dot_time"] and dots_found["breakout_time"]:
            message = f"Pattern found for {ticker_symbol}"
        else:
            message = f"Pattern partially found for {ticker_symbol}"

        dots_found["message"] = message
        dots_found["first_big_green_dot_time"] = big_green_dot['TV Time']
        print("Debug: Big Green Dot Time:", dots_found["first_big_green_dot_time"])
        
        return dots_found



# Utility Functions


def fetch_data_for_plan(plan):
    # Fetch data for a given plan based on its settings (ticker, time frame, etc.)
    pass


def update_ui_for_plan(plan, strategy_result):
    # Update the SQLite database to reflect changes in the UI for a given plan and strategy result
    pass
