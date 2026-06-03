# generate_session.py
from pyrogram import Client
import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")

print("Initializing Pyrogram to generate session string...")
app = Client("netradrive_temp", api_id=API_ID, api_hash=API_HASH)

with app:
    session_string = app.export_session_string()
    print("\n--- COPY THE STRING BELOW ---")
    print(session_string)
    print("-----------------------------\n")
    print("Add this string to your .env file as TELEGRAM_SESSION_STRING.")
