"""Internal ML classifier for ticket problem categories (no external API).

Pipeline: normalize Persian text -> append keyword-hint tokens -> TF-IDF (word + char n-grams)
-> LogisticRegression trained on bot/data/seed_training.csv at startup.
Unsure tickets are reported as "نیازمند تصمیم" or borderline. To improve accuracy, add rows to the CSV.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from .persian import normalize

SEED_FILE = Path(__file__).parent / "data" / "seed_training.csv"

# Order of the 13 categories from the analysis prompt.
CATEGORIES = [
    "مغایرت نمایش بسته", "بسته رزرو", "فعال‌سازی بسته", "فعال‌سازی بسته مودم",
    "فعال‌سازی بسته هدیه", "لغو تمدید خودکار", "لغو بسته و استرداد", "اولویت بسته",
    "عدم ارسال کد هدیه", "عدم محاسبه صحیح حجم", "مغایرت حجم بسته", "مشکل بسته روبیکا",
    "دوشنبه سوری",
]
NEEDS_DECISION = "نیازمند تصمیم"

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
    "hint_modem": r"مودم",
    "hint_code": r"کد دیجیتال|فیلیمو|دیجی ?کالا|کد تخفیف|کد هدیه",
    "hint_rubika": r"روبیکا|روبینو|ویترین|آی ?نو|ای ?نو",
    "hint_double": r"دو ?بار|همزمان|هم زمان",
    "hint_remaining": r"باقی ?مانده|دو استعلام",
    "hint_monday": r"دوشنبه سوری",
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
            ("clf", LogisticRegression(C=100, max_iter=2000, class_weight="balanced")),
        ])
        self.model.fit(texts, labels)
        # the CSV may use plain spaces; map back to the canonical names
        self._canon = {normalize(c): c for c in CATEGORIES}

    def predict(self, texts: list[str]) -> list[dict]:
        """Per text: top label/confidence and the runner-up (used to flag borderline tickets)."""
        if not texts:
            return []
        proba = self.model.predict_proba(texts)
        classes = [self._canon.get(c, c) for c in self.model.classes_]
        out = []
        for row in proba:
            order = row.argsort()[::-1]
            a, b = int(order[0]), int(order[1])
            out.append({"label": classes[a], "conf": float(row[a]),
                        "second": classes[b], "second_conf": float(row[b])})
        return out
