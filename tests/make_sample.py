"""Synthetic Behsa_Report-style workbook (no real customer data)."""
import csv
from pathlib import Path

import pandas as pd

SEED = Path(__file__).resolve().parent.parent / "bot" / "data" / "seed_training.csv"


def make_sample(path):
    rows = list(csv.DictReader(open(SEED, encoding="utf-8")))
    recs = []
    for i, r in enumerate(rows[:40]):
        recs.append({
            "شماره تیکت": 20261122000000 + i, "نوع درخواست خدمات": "بسته ها", "دسته مشکل": "عدم یا ارائه ناقص سرویس",
            "درگاه": "Manual", "تاریخ تولید": f"1405/09/01 {8 + i % 12:02d}:10:00", "شماره موبایل": "09123456789",
            "استان": "تهران", "نام بسته": "بسته نمونه", "نوع بسته و شارژ": "30 روزه", "حجم بسته": "10 GB",
            "نوع مشکل تایپ": "", "محتوای خدمات": r["text"] + " تماس 09121112233", "شکایت سامانه 195": None})
    pd.DataFrame(recs).to_excel(path, index=False)
    return path


if __name__ == "__main__":
    import sys
    make_sample(sys.argv[1] if len(sys.argv) > 1 else "Behsa_Report_sample.xlsx")
