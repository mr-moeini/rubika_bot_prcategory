"""Synthetic Behsa_Report-style workbook (no real customer data)."""
import csv
from pathlib import Path

import pandas as pd

SEED = Path(__file__).resolve().parent.parent / "bot" / "data" / "seed_training.csv"
PKG = "[6] بسته ها > [6-8]مشکلات بسته"
EXTRA = [  # (type, text) rows that must be excluded by step 1
    ("درخواست لغو بسته(مشتری مداری)", "مشترک بسته را خریده و درخواست لغو دارد"),
    ("مشکل فعالسازی", "تیکت جهت حفظ تعامل با مشترک ثبت شده است"),
    ("مشکل فعالسازی", "سیم کارت قطع یکطرفه بدهی است و نمی تواند تماس بگیرد"),
    ("مشکل فعالسازی", "مشترک بسته را اشتباه خریده است"),
]


def make_sample(path, with_other_services=False):
    rows = list(csv.DictReader(open(SEED, encoding="utf-8")))
    texts = [("", r["text"]) for r in rows[::2][:40]] + EXTRA
    recs = []
    for i, (typ, text) in enumerate(texts):
        recs.append({
            "شماره تیکت": 20261122000000 + i, "نوع درخواست خدمات": PKG, "دسته مشکل": "عدم یا ارائه ناقص سرویس",
            "درگاه": "Manual", "تاریخ تولید": f"1405/09/01 {8 + i % 12:02d}:10:00", "شماره موبایل": "09123456789",
            "استان": "تهران", "نام بسته": "بسته نمونه", "نوع بسته و شارژ": "30 روزه", "حجم بسته": "10 GB",
            "نوع مشکل تایپ": typ, "محتوای خدمات": text + " تماس 09121112233", "شکایت سامانه 195": None})
    if with_other_services:
        recs.append({**recs[0], "شماره تیکت": 1, "نوع درخواست خدمات": "[3] شارژ > [3-1] مشکل شارژ",
                     "محتوای خدمات": "شارژ اعمال نشد"})
    pd.DataFrame(recs).to_excel(path, index=False, sheet_name="Behsa Report")
    return path, len(texts)


if __name__ == "__main__":
    import sys
    make_sample(sys.argv[1] if len(sys.argv) > 1 else "Behsa_Report_sample.xlsx")
