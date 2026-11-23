import io

from openpyxl import load_workbook

from bot.categorizer import TicketCategorizer
from bot.config import Settings
from bot.main import extract_file_message
from bot.persian import normalize
from bot.report import build_report
from bot.rules import check_exclusion, hard_category
from tests.make_sample import make_sample

CAT = TicketCategorizer()


def test_normalize():
    assert normalize("ي ك ۱۲") == "ی ک 12"


def test_file_pattern_and_filter():
    s = Settings()
    up = {"type": "NewMessage", "chat_id": "g0x", "new_message": {
        "message_id": "1", "sender_type": "User", "file": {"file_id": "f", "file_name": "Behsa_Report_49_tickets.xlsx"}}}
    assert extract_file_message(up, s) == ("g0x", "1", "f", "Behsa_Report_49_tickets.xlsx")
    up["new_message"]["file"]["file_name"] = "other.xlsx"
    assert extract_file_message(up, s) is None


def test_exclusion_rules():
    assert check_exclusion("سیم کارت قطع یکطرفه بدهی", "", False)[0] == 6
    assert check_exclusion("جهت حفظ تعامل ثبت شد", "", False)[0] == 1
    assert check_exclusion("بسته را اشتباه خریده", "", False)[0] == 2
    assert check_exclusion("سرعت اینترنت پایین است", "", False)[0] == 3
    assert check_exclusion("بسته در نمای کلی هست", "", True) is None
    assert check_exclusion("حجم تمام شد", "درخواست لغو بسته(مشتری مداری)", True)[2] is True


def test_hard_rules():
    assert hard_category("بسته دوشنبه سوری فعال نشد", "") == "دوشنبه سوری"
    assert hard_category("کد دیجیتال فیلیمو ارسال نشده", "") == "عدم ارسال کد هدیه"
    assert hard_category("کد فیلیمو دوبار کسر شد و همزمان فعال شد", "") is None


def test_categories():
    cases = {
        "بسته در نمای کلی رزرو است ولی در طرح رایگان فعال است": "مغایرت نمایش بسته",
        "مودم خریداری شد و بسته 300 گیگ فعال نشده": "فعال‌سازی بسته مودم",
        "کد لغو تمدید زده شد اما بسته تمدید شد": "لغو تمدید خودکار",
    }
    for text, want in cases.items():
        assert CAT.predict([text])[0]["label"] == want


def test_end_to_end(tmp_path):
    p, n = make_sample(tmp_path / "Behsa_Report_x.xlsx")
    rep = build_report(p.read_bytes(), Settings(), CAT)
    assert rep.png[:8] == b"\x89PNG\r\n\x1a\n"
    assert "حذف‌شده: ۴ تیکت" in rep.caption and any("ردیف" in m for m in rep.messages)
    wb = load_workbook(io.BytesIO(rep.xlsx))
    assert wb.sheetnames == ["Behsa Report", "Summerty"]
    ws = wb["Behsa Report"]
    headers = [c.value for c in ws[1]]
    assert "شماره موبایل" not in headers and headers[-1] == "Category"
    assert ws.max_row == n - 4 + 1  # excluded rows removed
    assert wb["Summerty"]["B2"].value.startswith("=COUNTIF(")
    assert not any("09121112233" in str(c.value) for r in ws.iter_rows() for c in r)


def test_full_mode_keeps_rows(tmp_path):
    p, n = make_sample(tmp_path / "Behsa_Report_x.xlsx", with_other_services=True)
    rep = build_report(p.read_bytes(), Settings(), CAT)
    ws = load_workbook(io.BytesIO(rep.xlsx))["Behsa Report"]
    headers = [c.value for c in ws[1]]
    assert headers[-3:] == ["Category", "نوع خدمت", "زیردسته"]
    assert ws.max_row == n + 1 + 1
    cats = [ws.cell(row=r, column=len(headers) - 2).value for r in range(2, ws.max_row + 1)]
    assert cats.count("خارج از تحلیل") == 4
