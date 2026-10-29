"""Send alerts to any configured channel (configured via env vars)."""
import os
import socket

import requests

HOST = socket.gethostname()
ICON = {"critical": "🔴", "warning": "🟠", "resolved": "🟢"}


def send(severity, message):
    text = f"{ICON.get(severity, '')} [{HOST}] {severity.upper()}: {message}"
    print(text, flush=True)

    if os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        _post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/sendMessage",
              {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text})
    if os.getenv("SLACK_WEBHOOK_URL"):
        _post(os.environ["SLACK_WEBHOOK_URL"], {"text": text})
    if os.getenv("DISCORD_WEBHOOK_URL"):
        _post(os.environ["DISCORD_WEBHOOK_URL"], {"content": text})
    if os.getenv("WEBHOOK_URL"):
        _post(os.environ["WEBHOOK_URL"],
              {"host": HOST, "severity": severity, "message": message})


def _post(url, payload):
    try:
        requests.post(url, json=payload, timeout=10).raise_for_status()
    except Exception as e:
        print(f"notifier error: {e}", flush=True)
