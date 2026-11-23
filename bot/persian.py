"""Persian text helpers: normalization, digits, Jalali month names, RTL shaping."""
import re

import arabic_reshaper
from bidi.algorithm import get_display

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_AR_TO_EN = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670\u0640]")
JALALI_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                 "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]

_reshaper = arabic_reshaper.ArabicReshaper(configuration={"delete_harakat": True})


def fa_digits(text) -> str:
    return str(text).translate(_FA_DIGITS)


def normalize(text) -> str:
    """Unify Arabic/Persian letter forms and digits, ZWNJ -> space, squeeze spaces."""
    t = "" if text is None else str(text)
    t = t.translate(_AR_TO_EN)
    t = t.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه").replace("ۀ", "ه")
    t = t.replace("\u200c", " ").replace("\u200f", " ").replace("\u200e", " ")
    t = _DIACRITICS.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


def rtl(text) -> str:
    """Shape + reorder text so Pillow (which has no bidi support) draws it correctly."""
    return get_display(_reshaper.reshape(str(text)))
