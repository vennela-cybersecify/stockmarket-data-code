

import os
import time
from datetime import datetime
from kiteconnect import KiteConnect
import pandas as pd
from playwright.sync_api import sync_playwright
import pyotp
from flask import Flask, request
from threading import Thread

# Flask App Initialization
app = Flask(__name__)

request_token_global = None  # Global variable to capture the request token


@app.route("/")
def capture_request_token():
    global request_token_global
    request_token = request.args.get("request_token")
    if request_token:
        request_token_global = request_token
        return f"Request Token Captured: {request_token}", 200
    return "No Request Token Found", 400


# Kite Connect initialization
api_key = "kamk9sas6i548q1u"  # Replace with your API key
api_secret = "2846tantq1bayvuow18qkzh56t4a5o9i"  # Replace with your API secret
kite = KiteConnect(api_key=api_key)

# Replace with your TOTP secret key from the authenticator app setup
totp_secret = "YHXVZBZ3QEZYAONSLXNCERTEQTVWTTYV"  # Replace with your TOTP secret


def generate_totp():
    """
    Generate the TOTP using the shared secret key.
    """
    try:
        totp = pyotp.TOTP(totp_secret)
        code = totp.now()
        print(f"[INFO] Generated TOTP: {code}")
        return code
    except Exception as e:
        print(f"[ERROR] Error generating TOTP: {e}")
        raise


def automate_login():
    """
    Automate the login process using Playwright to fetch the request token.
    """
    with sync_playwright() as p:
        print("[INFO] Launching browser...")
        browser = p.chromium.launch(headless=False)  # Launch the browser
        context = browser.new_context()
        page = context.new_page()

        # Open the Kite login page
        print("[INFO] Opening Kite login page...")
        login_url = kite.login_url()
        print(f"[DEBUG] Login URL: {login_url}")
        page.goto(login_url)

        try:
            # Enter credentials
            print("[INFO] Entering credentials...")
            page.fill("input#userid", "GBD534")  # Replace with your Zerodha User ID
            page.fill("input#password", "Vennela@2001")  # Replace with your Zerodha Password

            # Click login button
            page.click("button.button-orange.wide")
            print("[INFO] Clicked on login button.")

            # Enter TOTP
            print("[INFO] Generating TOTP...")
            totp_code = generate_totp()
            page.wait_for_selector("input[type='number']", timeout=20000)
            page.fill("input[type='number']", totp_code)
            print("[INFO] TOTP entered. Waiting for redirection...")

            # Wait for the redirect
            page.wait_for_url("http://127.0.0.1:5000/*", timeout=60000)
            print("[INFO] Redirection successful. Check Flask app logs for request token.")

        except Exception as e:
            print(f"[ERROR] Error during login: {e}")
            raise
        finally:
            browser.close()


def generate_access_token(request_token):
    """
    Generate the access token using the request token.
    """
    print("[INFO] Generating access token...")
    try:
        session_data = kite.generate_session(request_token, api_secret=api_secret)
        access_token = session_data["access_token"]
        print(f"[INFO] Access token generated successfully: {access_token}")
        return access_token
    except Exception as e:
        print(f"[ERROR] Error generating access token: {e}")
        raise


def fetch_historical_data(symbol, from_date, to_date, interval):
    """
    Fetch historical data for the given symbol.
    """
    print(f"[INFO] Fetching historical data for symbol: {symbol}")
    try:
        instruments = kite.instruments()
        instrument_token = next(
            (i["instrument_token"] for i in instruments if i["tradingsymbol"] == symbol),
            None,
        )
        if not instrument_token:
            print(f"[ERROR] Instrument token not found for symbol: {symbol}")
            return None

        data = kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=interval,
        )
        print(f"[INFO] Historical data fetched successfully for {symbol}")
        return data
    except Exception as e:
        print(f"[ERROR] Error fetching historical data for {symbol}: {e}")
        raise


def store_historical_data(symbol, historical_data):
    """
    Store the fetched historical data in a separate folder and file for each symbol.
    """
    print(f"[INFO] Storing data for {symbol}...")
    base_dir = os.path.join(os.getcwd(), "historical_data")
    ticker_dir = os.path.join(base_dir, symbol)
    os.makedirs(ticker_dir, exist_ok=True)
    file_path = os.path.join(ticker_dir, f"{symbol}_historical_data.csv")
    try:
        pd.DataFrame(historical_data).to_csv(file_path, index=False)
        print(f"[INFO] Data for {symbol} saved to {file_path}")
        return file_path
    except Exception as e:
        print(f"[ERROR] Error saving data for {symbol}: {e}")
        raise


def process_tickers(file_path, from_date, to_date, interval):
    """
    Read ticker symbols from a file and fetch & save their historical data.
    """
    try:
        with open(file_path, "r") as f:
            tickers = [line.strip() for line in f if line.strip()]

        for symbol in tickers:
            historical_data = fetch_historical_data(symbol, from_date, to_date, interval)
            if historical_data:
                store_historical_data(symbol, historical_data)
            else:
                print(f"[WARNING] No data found for {symbol}")
    except FileNotFoundError:
        print(f"[ERROR] Ticker file not found: {file_path}")
        raise
    except Exception as e:
        print(f"[ERROR] Error processing tickers: {e}")
        raise


# Run Flask server in a separate thread
def run_flask_app():
    from waitress import serve
    print("[INFO] Starting Flask server...")
    serve(app, host="127.0.0.1", port=5000)


if __name__ == "__main__":
    try:
        # Start Flask app in a separate thread
        flask_thread = Thread(target=run_flask_app)
        flask_thread.daemon = True
        flask_thread.start()

        # Automate login and capture request token
        automate_login()

        # Wait for the request token to be captured
        while request_token_global is None:
            print("[INFO] Waiting for request token...")
            time.sleep(1)

        print(f"[INFO] Request token captured: {request_token_global}")

        # Generate access token
        access_token = generate_access_token(request_token_global)
        kite.set_access_token(access_token)

        # Read tickers from file and fetch & save their historical data
        ticker_file = "tickers.txt"  # Replace with your ticker file path
        from_date = "2023-01-01"
        to_date = datetime.now().strftime("%Y-%m-%d")
        interval = "day"

        process_tickers(ticker_file, from_date, to_date, interval)

    except Exception as e:
        print(f"[FATAL ERROR] {e}")
