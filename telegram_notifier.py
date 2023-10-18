import os
from dotenv import load_dotenv
import requests

load_dotenv(dotenv_path="./.env")

TELE_TOKEN = os.getenv("TELE_TOKEN")

TOKEN = TELE_TOKEN
CHAT_ID = "-1004052876483"

def send_telegram_message(message):
    base_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    response = requests.post(base_url, data=payload)
    response_json = response.json()

    if not response_json.get("ok"):
        print(f"Failed to send message. Error: {response_json.get('description')}")

    return response_json

