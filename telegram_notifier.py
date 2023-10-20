import os
from dotenv import load_dotenv
import requests

load_dotenv(dotenv_path="./.env")

TELE_TOKEN = os.getenv("TELE_TOKEN")
TELE_CHAT_ID = os.getenv("TELE_CHAT_ID")
TOKEN = TELE_TOKEN
CHAT_ID = TELE_CHAT_ID #Chat ID

def send_telegram_message(message):
    base_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    response = requests.post(base_url, data=payload)
    response_data = response.json()
    
    # Check for error in the response and raise exception with details
    if not response_data.get("ok"):
        raise Exception(f"Telegram API Error: {response_data.get('description', 'Unknown error')}")
    
    return response_data
