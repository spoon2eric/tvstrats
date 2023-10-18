import os
from dotenv import load_dotenv
import requests

load_dotenv(dotenv_path="./.env")

TELE_TOKEN = os.getenv("TELE_TOKEN")

TOKEN = {TELE_TOKEN}  # Replace with your bot token
CHAT_ID = "@TV Alerts"  # Replace with your channel's name or chat ID

def send_telegram_message(message):
    base_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    response = requests.post(base_url, data=payload)
    return response.json()
