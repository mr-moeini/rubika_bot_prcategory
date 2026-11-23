import re

import pandas as pd

from bot.categorizer import TicketCategorizer
from bot.config import Settings
from bot.main import extract_file_message
from bot.persian import normalize
from bot.report import build_report, clean_excel, summarize
from tests.make_sample import make_sample


def test_normalize():
    assert normalize("ي ك ۱۲") == "ی ک 12"


def test_file_pattern_and_filter():
    s = Settings()
    up = {"type": "NewMessage", "chat_id": "g0x", "new_message": {
        "message_id": "1", "sender_type": "User", "file": {"file_id": "f", "file_name": "Behsa_Report_49_tickets.xlsx"}}}
    assert extract_file_message(up, s) == ("g0x", "1", "f", "Behsa_Report_49_tickets.xlsx")
    up["new_message"]["file"]["file_name"] = "other.xlsx"
    assert extract_file_message(up, s) is None


def test_clean_drops_mobile(tmp_path):
    p = make_sample(tmp_path / "Behsa_Report_x.xlsx")
    df = clean_excel(p.read_bytes(), Settings())
    assert "شماره موبایل" not in df.columns
    assert not any(re.search(r"09\d{9}", str(v)) for v in df["محتوای خدمات"])


def test_categories():
    c = TicketCategorizer()
    cases = {
        "بسته در نمای کلی رزرو است ولی در طرح رایگان فعال است": "مغایرت نمایش بسته",
        "مودم خریداری شد بسته هدیه فعال نشده": "فعال‌سازی بسته هدیه",
        "کد لغو تمدید زده شد اما بسته تمدید شد": "لغو تمدید خودکار",
    }
    for text, want in cases.items():
        assert c.predict([text])[0][0] == want


def test_end_to_end(tmp_path):
    p = make_sample(tmp_path / "Behsa_Report_x.xlsx")
    png, caption, xlsx = build_report(p.read_bytes(), Settings(), TicketCategorizer())
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and "جمع کل" in caption
    out = pd.read_excel(__import__("io").BytesIO(xlsx), sheet_name=None)
    assert "شماره موبایل" not in out["تیکت‌ها"].columns
    assert summarize(out["تیکت‌ها"])["تعداد تیکت"].sum() == 40
