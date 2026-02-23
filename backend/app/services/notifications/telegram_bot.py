import requests

from app.core.config import settings


class TelegramNotifier:
    def __init__(self) -> None:
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id

    def send(self, message: str) -> bool:
        if not self.token or not self.chat_id:
            return False

        url = f'https://api.telegram.org/bot{self.token}/sendMessage'
        payload = {'chat_id': self.chat_id, 'text': message}
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200