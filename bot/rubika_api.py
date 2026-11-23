"""Minimal client for the official Rubika Bot API (https://botapi.rubika.ir/v3/<TOKEN>/<method>).

Get the token from @botfather inside Rubika. Kept tiny and isolated so endpoint/field tweaks
only touch this file.
"""
from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger("rubika")
BASE = "https://botapi.rubika.ir/v3"


class RubikaError(RuntimeError):
    pass


class RubikaClient:
    def __init__(self, token: str, timeout: int = 60):
        if not token:
            raise RubikaError("RUBIKA_BOT_TOKEN is empty")
        self.url = f"{BASE}/{token}"
        self.timeout = timeout
        self.http = requests.Session()

    def call(self, method: str, payload: dict | None = None, retries: int = 3) -> dict:
        last = None
        for attempt in range(retries):
            try:
                r = self.http.post(f"{self.url}/{method}", json=payload or {}, timeout=self.timeout)
                r.raise_for_status()
                body = r.json()
                if body.get("status") not in (None, "OK"):
                    raise RubikaError(f"{method}: {body}")
                return body.get("data", body)
            except (requests.RequestException, ValueError) as exc:
                last = exc
                time.sleep(1.5 * (attempt + 1))
        raise RubikaError(f"{method} failed: {last}")

    # ---- updates -------------------------------------------------------
    def get_updates(self, offset_id: str | None = None, limit: int = 50) -> tuple[list[dict], str | None]:
        payload = {"limit": limit}
        if offset_id:
            payload["offset_id"] = offset_id
        data = self.call("getUpdates", payload)
        return data.get("updates", []) or [], data.get("next_offset_id")

    # ---- files ---------------------------------------------------------
    def download_file(self, file_id: str) -> bytes:
        info = self.call("getFile", {"file_id": file_id})
        r = self.http.get(info["download_url"], timeout=self.timeout * 2)
        r.raise_for_status()
        return r.content

    def send_message(self, chat_id: str, text: str, reply_to: str | None = None) -> dict:
        payload = {"chat_id": chat_id, "text": text}
        if reply_to:
            payload["reply_to_message_id"] = reply_to
        return self.call("sendMessage", payload)

    def send_file(self, chat_id: str, content: bytes, file_name: str, kind: str = "File",
                  caption: str | None = None, reply_to: str | None = None) -> dict:
        """kind: 'File' | 'Image'. Flow: requestSendFile -> upload -> sendFile."""
        upload_url = self.call("requestSendFile", {"type": kind})["upload_url"]
        r = self.http.post(upload_url, files={"file": (file_name, content)}, timeout=self.timeout * 3)
        r.raise_for_status()
        file_id = r.json()["data"]["file_id"]
        payload = {"chat_id": chat_id, "file_id": file_id}
        if caption:
            payload["text"] = caption
        if reply_to:
            payload["reply_to_message_id"] = reply_to
        return self.call("sendFile", payload)
