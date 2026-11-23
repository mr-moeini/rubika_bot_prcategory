"""Internal ML classifier for ticket problem categories (no external API).

Pipeline: normalize Persian text -> append keyword-hint tokens -> TF-IDF (word + char n-grams)
-> LogisticRegression trained on bot/data/seed_training.csv at startup.
Low-confidence tickets fall into "سایر موارد". To improve accuracy, just add rows to the CSV.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from .persian import normalize

SEED_FILE = Path(__file__).parent / "data" / "seed_training.csv"
OTHER = "سایر موارد"

# Display order == order in the report (OTHER is always last).
CATEGORIES = [
    "مغایرت نمایش بسته", "بسته رزرو", "لغو تمدید خودکار", "فعال‌سازی بسته",
    "فعال‌سازی بسته هدیه", "لغو بسته و استرداد", "اولویت بسته",
    "عدم محاسبه صحیح حجم", OTHER,
]

# Keyword hints become extra tokens so the model can lean on strong domain signals.
_HINTS = {
    "hint_display": r"نمای کلی|نما کلی|طرح(?:های)? رایگان|طرح رایگاه|استعلام|مغایرت",
    "hint_reserve": r"رزرو|رزو",
    "hint_renew": r"لغو تمدید|تمدید خودکار|خودکار.*تمدید|تمدید.*لغو|کد لغو|ستاره 100",
    "hint_gift": r"هدیه|هدیه ای",
    "hint_activate": r"فعال نشد|فعال نشده|فعال نمی ?شود|فعال ?سازی",
    "hint_refund": r"عودت|استرداد|درخواست لغو|لغو بسته|حذف بسته|اشتباه خرید|مشتری مداری",
    "hint_priority": r"اولویت",
    "hint_volume": r"کسر|محاسبه|تمام شد|مصرف",
}
_HINTS = {k: re.compile(v) for k, v in _HINTS.items()}


def build_text(*parts) -> str:
    text = normalize(" ".join("" if p is None or (isinstance(p, float) and p != p) else str(p)
                              for p in parts))
    hints = " ".join(k for k, rx in _HINTS.items() if rx.search(text))
    return f"{text} {hints}".strip()


class TicketCategorizer:
    def __init__(self, seed_file: Path = SEED_FILE, min_confidence: float = 0.30):
        self.min_confidence = min_confidence
        with open(seed_file, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        texts = [build_text(r["text"]) for r in rows]
        labels = [normalize(r["label"]) for r in rows]
        self.model = Pipeline([
            ("tfidf", FeatureUnion([
                ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)),
                ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4),
                                         sublinear_tf=True, min_df=1)),
            ])),
            ("clf", LogisticRegression(C=20, max_iter=2000, class_weight="balanced")),
        ])
        self.model.fit(texts, labels)
        # the CSV may use plain spaces; map back to the canonical names
        self._canon = {normalize(c): c for c in CATEGORIES}

    def predict(self, texts: list[str]) -> list[tuple[str, float]]:
        if not texts:
            return []
        proba = self.model.predict_proba(texts)
        classes = self.model.classes_
        out = []
        for row in proba:
            i = int(row.argmax())
            label = self._canon.get(classes[i], classes[i])
            conf = float(row[i])
            out.append((OTHER if conf < self.min_confidence else label, conf))
        return out

    def categorize_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Adds 'دسته‌بندی' and 'اطمینان' columns, reading the ticket text columns if present."""
        cols = [c for c in ("نوع مشکل تایپ", "نام بسته", "محتوای خدمات") if c in df.columns]
        if not cols:  # fall back to every text column
            cols = [c for c in df.columns if pd.api.types.is_string_dtype(df[c]) or df[c].dtype == object]
        texts = [build_text(*row) for row in df[cols].itertuples(index=False, name=None)]
        preds = self.predict(texts)
        df = df.copy()
        df["دسته‌بندی"] = [p[0] for p in preds]
        df["اطمینان"] = [round(p[1], 2) for p in preds]
        return df
