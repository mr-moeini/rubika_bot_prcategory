"""Poll Rubika, react to Behsa_Report*.xlsx files, post categorized PNG back to the group."""
from __future__ import annotations

import argparse
import json
import logging
import time

from .categorizer import TicketCategorizer
from .config import Settings
from .report import build_report
from .rubika_api import RubikaClient, RubikaError

log = logging.getLogger("bot")


def load_state(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {"offset_id": None, "done": []}


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    state["done"] = state["done"][-500:]
    path.write_text(json.dumps(state))


def extract_file_message(update: dict, settings: Settings):
    """Return (chat_id, message_id, file_id, file_name) if this update is a matching Excel upload."""
    if update.get("type") != "NewMessage":
        return None
    msg = update.get("new_message") or {}
    if msg.get("sender_type") == "Bot":
        return None
    f = msg.get("file") or {}
    name = f.get("file_name") or ""
    chat_id = update.get("chat_id")
    if not f.get("file_id") or not settings.file_pattern.match(name):
        return None
    if settings.allowed_chats and chat_id not in settings.allowed_chats:
        return None
    return chat_id, msg.get("message_id"), f["file_id"], name


def handle(client, settings, categorizer, chat_id, message_id, file_id, name):
    log.info("processing %s in %s", name, chat_id)
    data = client.download_file(file_id)
    png, caption, xlsx = build_report(data, settings, categorizer)
    client.send_file(chat_id, png, "ticket_categories.png", kind="Image", caption=caption,
                     reply_to=message_id)
    if settings.send_xlsx:
        client.send_file(chat_id, xlsx, f"categorized_{name}", kind="File",
                         caption="فایل دسته‌بندی‌شده (بدون ستون شماره موبایل)")


def run(once: bool = False):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings()
    client = RubikaClient(settings.token)
    categorizer = TicketCategorizer(min_confidence=settings.min_confidence)
    state = load_state(settings.state_file)

    first_run = state["offset_id"] is None
    while True:
        try:
            updates, next_offset = client.get_updates(state["offset_id"])
            skip = first_run and not settings.process_backlog
            for up in updates:
                hit = extract_file_message(up, settings)
                if not hit or skip or hit[1] in state["done"]:
                    continue
                try:
                    handle(client, settings, categorizer, *hit)
                except Exception:  # keep the bot alive; tell the group something went wrong
                    log.exception("failed to process %s", hit[3])
                    try:
                        client.send_message(hit[0], "⚠️ پردازش فایل با خطا مواجه شد.", reply_to=hit[1])
                    except RubikaError:
                        pass
                state["done"].append(hit[1])
            if next_offset:
                state["offset_id"] = next_offset
            first_run = False
            save_state(settings.state_file, state)
        except RubikaError as exc:
            log.warning("api error: %s", exc)
        if once:
            return
        time.sleep(settings.poll_interval)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="poll one time and exit")
    run(ap.parse_args().once)
