import requests


def send_webhook(url: str, payload: dict) -> bool:
    response = requests.post(url, json=payload, timeout=10)
    return 200 <= response.status_code < 300