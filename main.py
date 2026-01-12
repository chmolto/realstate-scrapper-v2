import os
import json
import base64
import requests
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("IDEALISTA_API_KEY")
API_SECRET = os.getenv("IDEALISTA_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HISTORY_FILE = "history.json"

def get_access_token():
    url = "https://api.idealista.com/oauth/token"
    # Create Basic Auth header
    auth_str = f"{API_KEY}:{API_SECRET}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials", "scope": "read"}
    
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()["access_token"]
    except Exception as e:
        print(f"Error getting token: {e}")
        try:
            print(f"Response: {response.text}")
        except:
            pass
        sys.exit(1)

def search_homes(token):
    # SEARCH PARAMETERS
    # IMPORTANT: You need to set 'center' and 'distance' or usage 'locationId'.
    # Defaulting to Madrid Center for demonstration.
    # Replace '40.4167,-3.70325' with your target coordinates.
    # Previous URL had: price 80k-150k, 3+ bedrooms, garage, lift.
    
    base_url = "https://api.idealista.com/3.5/es/search"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    params = {
        "country": "es",
        "operation": "sale",
        "propertyType": "homes",
        "center": "40.4167,-3.70325", # MADRID - CHANGE THIS!
        "distance": "10000",           # 10km radius
        "minPrice": "80000",
        "maxPrice": "150000",
        "minBedrooms": "3",
        "hasLift": "true",
        "hasParkingSpace": "true",
        # "sinceDate": "W" # Last week. Remove to get all.
    }
    
    try:
        print("Searching Idealista API...")
        response = requests.post(base_url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get("elementList", [])
    except Exception as e:
        print(f"Error during search: {e}")
        try:
            print(f"Response: {response.text}")
        except:
            pass
        return []

def send_telegram(item):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram configuration missing.")
        return

    title = item.get("suggestedTexts", {}).get("title", item.get("address", "New Listing"))
    price = item.get("price", "N/A")
    url = item.get("url", "")
    
    msg = (
        f"🏠 *New API Listing*\n\n"
        f"*{title}*\n"
        f"💰 {price} €\n"
        f"🔗 [View Listing]({url})"
    )
    
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    
    try:
        requests.post(tg_url, json=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

def main():
    print("--- Starting API Job ---")
    
    # 1. Load History
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        except:
            history = []
    
    # 2. Authenticate
    if not API_KEY or not API_SECRET:
        print("Missing API Keys (IDEALISTA_API_KEY/SECRET). Check .env")
        sys.exit(1)
        
    token = get_access_token()
    print("Authenticated successfully.")
    
    # 3. Search
    results = search_homes(token)
    print(f"Found {len(results)} items via API.")
    
    # 4. Filter & Notify
    new_count = 0
    history_set = set(history)
    
    for item in results:
        prop_id = str(item.get("propertyCode"))
        if prop_id not in history_set:
            new_count += 1
            print(f"New property: {prop_id}")
            send_telegram(item)
            history.append(prop_id)
            history_set.add(prop_id)
            
    # 5. Save History
    if new_count > 0:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f)
        print(f"Sent {new_count} notifications. History updated.")
    else:
        print("No new listings found.")
        
    print("--- Done ---")

if __name__ == "__main__":
    main()
