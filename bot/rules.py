"""Step 1 of the analysis prompt: tickets that are excluded from the analysis, plus hard category rules."""
from __future__ import annotations

import re

from .persian import normalize

NA = r"(?<![آ-ی])"      # not preceded by a Persian letter
NB = r"(?![آ-ی])"       # not followed by a Persian letter

# (rule number, reason shown in the report, regex over the normalized 'محتوای خدمات')
EXCLUDE_RULES = [
    (1, "ثبت به‌خاطر مشتری‌مداری / حفظ تعامل / اصرار مشترک",
     r"مشتری ?مداری|حفظ تعامل|جهت تعامل|تعامل تیکت|به اصرار"),
    (2, "اشتباه کاربر (خرید اشتباه / شماره دیگر / اعتراض به قانون بسته گیمر یا شبانت)",
     rf"اشتباه(?:ی)? (?:خرید|خریده|فعال|زده)|برای شماره (?:ی )?(?:دیگر|دیگری)|{NA}گیمر{NB}|شبانت.{{0,40}}نامحدود|نامحدود.{{0,40}}شبانت"),
    (3, "اختلال یا مشکل شبکه (کندی، قطعی، ضعف آنتن)",
     rf"{NA}کندی|سرعت (?:اینترنت |نت )?(?:پایین|کم|ضعیف)|افت سرعت|{NA}قطعی|ضعف آنتن|آنتن ?دهی|{NA}پینگ|نت (?:کند|ضعیف)"),
    (5, "اعتراض به تغییر قیمت بسته",
     rf"تغییر قیمت|قیمت (?:رزرو|بسته).{{0,40}}(?:فرق|متفاوت|اختلاف)|افزایش قیمت|{NA}گران(?:تر)?{NB}"),
    (6, "قطع میان‌دوره / قطع بدهی (مربوط به بسته نیست)",
     rf"قطع (?:یکطرفه|یک طرفه|دوطرفه|دو طرفه|میان ?دوره)|{NA}بدهی"),
    (7, "پیامک اتمام بسته طبق سیستم ارسال شده",
     r"پیامک اتمام.{0,50}(?:نگرفت|دریافت نکرد|نیامد|نرسید|دریافت نشد)"),
]
EXCLUDE_RULES = [(n, why, re.compile(rx)) for n, why, rx in EXCLUDE_RULES]

# rule 4: pure follow-up / protest of an earlier ticket without a specific new problem
_FOLLOWUP = re.compile(r"پیگیری (?:مجدد )?تیکت|تیکت (?:قبل|قبلی)|اعتراض (?:مجدد|به تیکت)|تیکت شماره")
TYPE_RULE1 = "درخواست لغو بسته مشتری مداری"

_MONDAY = re.compile(r"دوشنبه سوری")
_CODE_OBJ = re.compile(r"کد (?:دیجیتال|دیجی ?کالا|تخفیف|هدیه|اشتراک)|فیلیمو|دیجی ?کالا")
_CODE_FAIL = re.compile(r"ارسال نشده|ارسال نشد|نیامده|نیامد|دریافت نکرده|دریافت نشده|نرسیده|نرسید|کار نمی ?کند")
_DOUBLE = re.compile(r"دو ?بار|همزمان|هم زمان")


def check_exclusion(content: str, type_text: str, has_category_hint: bool):
    """Returns (rule_no, reason, type_only) or None. type_only = excluded only by the (unreliable) type column."""
    c, t = normalize(content), normalize(type_text).replace("(", " ").replace(")", " ")
    t = re.sub(r"\s+", " ", t).strip()
    for no, why, rx in EXCLUDE_RULES:
        if rx.search(c):
            return no, why, False
    if t.startswith(TYPE_RULE1):
        return 1, "نوع مشکل «درخواست لغو بسته (مشتری مداری)»", True
    if _FOLLOWUP.search(c) and not has_category_hint:
        return 4, "فقط پیگیری/اعتراض به تیکت قبلی بدون مشکل مشخص", False
    return None


def hard_category(content: str, package_name: str):
    c = normalize(content) + " " + normalize(package_name)
    if _MONDAY.search(c):
        return "دوشنبه سوری"
    if _CODE_OBJ.search(c) and _CODE_FAIL.search(c) and not _DOUBLE.search(c):
        return "عدم ارسال کد هدیه"
    return None
