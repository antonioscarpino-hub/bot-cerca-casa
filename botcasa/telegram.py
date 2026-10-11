import logging
from typing import List, Optional

import requests

from . import config

log = logging.getLogger(__name__)


class Telegram:
    def __init__(self, token: str, session: Optional[requests.Session] = None):
        self.base = f"https://api.telegram.org/bot{token}/"
        self.session = session or requests.Session()

    def _call(self, method: str, **params):
        r = self.session.post(self.base + method, json=params, timeout=config.REQUEST_TIMEOUT)
        data = r.json()
        if not data.get("ok"):
            log.warning("Telegram %s: %s", method, data.get("description"))
        return data.get("result")

    def updates(self, offset: int) -> List[dict]:
        return self._call("getUpdates", offset=offset, timeout=0, allowed_updates=["message"]) or []

    def send(self, chat_id, text: str):
        # Telegram accetta al massimo 4096 caratteri per messaggio.
        for i in range(0, len(text), 4000):
            self._call("sendMessage", chat_id=chat_id, text=text[i:i + 4000], parse_mode="HTML",
                       disable_web_page_preview=False)
