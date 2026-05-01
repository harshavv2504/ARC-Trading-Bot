"""
Kite Connect daily authentication helper.

Run this every morning before the market opens:
    python kite_login.py

It will:
  1. Open the Kite login page in your browser
  2. Catch the redirect automatically (tiny local server on port 8000)
  3. Exchange the request_token for an access token
  4. Save it to .kite_token.json (auto-loaded by the bot on startup)
"""

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from kiteconnect import KiteConnect
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("KITE_API_KEY", "")
API_SECRET = os.getenv("KITE_API_SECRET", "")
TOKEN_FILE = Path(".kite_token.json")
CALLBACK_PORT = 8000
CALLBACK_PATH = "/api/kite/callback"


def save_token(token: str):
    TOKEN_FILE.write_text(json.dumps({"access_token": token}))
    print(f"\n  Token saved to {TOKEN_FILE}")


class CallbackHandler(BaseHTTPRequestHandler):
    access_token = None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return

        params = parse_qs(parsed.query)
        request_token = params.get("request_token", [None])[0]
        status = params.get("status", [""])[0]

        if status != "success" or not request_token:
            self._respond(500, "<h2>Login failed or cancelled.</h2>")
            print("\n  Login failed or cancelled.")
            return

        print(f"\n  request_token received: {request_token[:8]}...")
        try:
            kite = KiteConnect(api_key=API_KEY)
            data = kite.generate_session(request_token, api_secret=API_SECRET)
            token = data["access_token"]
            save_token(token)
            CallbackHandler.access_token = token
            self._respond(
                200,
                "<h2 style='font-family:sans-serif;color:green'>"
                "Kite authenticated! You can close this tab.</h2>"
                "<p style='font-family:sans-serif'>ARC Trading Bot is ready.</p>",
            )
            print(f"  Access token: {token[:8]}...{token[-4:]}")
            print("\n  Authentication successful. You can close the browser tab.")
        except Exception as e:
            self._respond(500, f"<h2>Token exchange failed: {e}</h2>")
            print(f"\n  Token exchange failed: {e}")

    def _respond(self, code: int, html: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass  # suppress request logs


def main():
    if not API_KEY or not API_SECRET:
        print("ERROR: KITE_API_KEY or KITE_API_SECRET not set in .env")
        return

    kite = KiteConnect(api_key=API_KEY)
    login_url = kite.login_url()

    print("=" * 55)
    print("  ARC Trading Bot — Kite Authentication")
    print("=" * 55)
    print(f"\n  Opening browser for Kite login...")
    print(f"  URL: {login_url}\n")

    webbrowser.open(login_url)

    server = HTTPServer(("127.0.0.1", CALLBACK_PORT), CallbackHandler)
    print(f"  Waiting for Kite callback on port {CALLBACK_PORT}...")
    print("  (Log in to Zerodha in the browser window)\n")

    # Handle requests until we get the token or user interrupts
    while CallbackHandler.access_token is None:
        server.handle_request()

    server.server_close()
    print("\n  Done. Start the bot with:")
    print("  venv/bin/uvicorn backend.main:app --reload\n")


if __name__ == "__main__":
    main()
