"""Excel cleaning + summary table + PNG rendering (Persian, RTL)."""
from __future__ import annotations

import io
import re
from datetime import datetime

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from .categorizer import CATEGORIES, TicketCategorizer
from .config import Settings
from .persian import JALALI_MONTHS, fa_digits, normalize, rtl

_PHONE = re.compile(r"(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)")


def clean_excel(data: bytes, settings: Settings) -> pd.DataFrame:
    """Read the workbook, drop the mobile-number column(s) and mask phone numbers in free text."""
    df = pd.read_excel(io.BytesIO(data))
    df.columns = [str(c).strip() for c in df.columns]
    drop = [c for c in df.columns if normalize(c) in {normalize(x) for x in settings.drop_columns}]
    df = df.drop(columns=drop)
    for col in df.columns:
        if pd.api.types.is_string_dtype(df[col]) or df[col].dtype == object:
            df[col] = df[col].map(lambda v: _PHONE.sub("[شماره حذف شد]", v) if isinstance(v, str) else v)
    return df


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    counts = df["دسته‌بندی"].value_counts()
    rows = [(c, int(counts.get(c, 0))) for c in CATEGORIES if counts.get(c, 0) > 0]
    rows.sort(key=lambda r: (-r[1], CATEGORIES.index(r[0])))
    if (o := [r for r in rows if r[0] == CATEGORIES[-1]]):
        rows = [r for r in rows if r[0] != CATEGORIES[-1]] + o
    total = sum(n for _, n in rows) or 1
    return pd.DataFrame({"دسته مشکل": [r[0] for r in rows], "تعداد تیکت": [r[1] for r in rows],
                         "درصد": [r[1] * 100 / total for r in rows]})


def report_title(df: pd.DataFrame) -> str:
    """'خلاصه مشکلات تیکت‌ها؛ ۱ آذر، ساعت ۱۴' from the latest 'تاریخ تولید' (Jalali) value."""
    if "تاریخ تولید" in df.columns:
        vals = df["تاریخ تولید"].dropna().astype(str).map(normalize)
        m = [re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):", v) for v in vals]
        m = [x for x in m if x]
        if m:
            last = max(m, key=lambda x: tuple(int(g) for g in x.groups()))
            month = JALALI_MONTHS[int(last.group(2)) - 1]
            return fa_digits(f"خلاصه مشکلات تیکت‌ها؛ {int(last.group(3))} {month}، ساعت {int(last.group(4))}")
    now = datetime.now()
    return fa_digits(f"خلاصه مشکلات تیکت‌ها؛ {now:%Y/%m/%d} ساعت {now.hour}")


def _hex(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def render_png(summary: pd.DataFrame, title: str, settings: Settings) -> bytes:
    S = 2  # supersample for crisp text
    W, row_h, head_h, title_h, pad = 760 * S, 38 * S, 42 * S, 58 * S, 14 * S
    n = len(summary)
    H = title_h + head_h + row_h * (n + 1) + pad
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_title = ImageFont.truetype(str(settings.font_bold), 21 * S, layout_engine=ImageFont.Layout.BASIC)
    f_head = ImageFont.truetype(str(settings.font_bold), 15 * S, layout_engine=ImageFont.Layout.BASIC)
    f_cell = ImageFont.truetype(str(settings.font_regular), 15 * S, layout_engine=ImageFont.Layout.BASIC)
    f_bold = ImageFont.truetype(str(settings.font_bold), 15 * S, layout_engine=ImageFont.Layout.BASIC)

    navy, navy_txt = _hex("#1f3864"), "white"
    x0, x1 = 12 * S, W - 12 * S
    # columns, drawn right->left like the Persian layout: category | count | percent
    w_cat, w_cnt = int((x1 - x0) * 0.46), int((x1 - x0) * 0.30)
    c_cat = (x1 - w_cat, x1)
    c_cnt = (c_cat[0] - w_cnt, c_cat[0])
    c_pct = (x0, c_cnt[0])

    def text_center(box, y, text, font, fill):
        t = rtl(text)
        w = d.textlength(t, font=font)
        asc = font.getbbox("Ag")[3]
        d.text(((box[0] + box[1]) / 2 - w / 2, y - asc / 2 - 2 * S), t, font=font, fill=fill)

    # title (right aligned)
    t = rtl(title)
    d.text((x1 - d.textlength(t, font=f_title), 12 * S), t, font=f_title, fill=navy)

    y = title_h
    d.rectangle([x0, y, x1, y + head_h], fill=navy)
    for box, label in ((c_pct, "درصد از کل"), (c_cnt, "تعداد تیکت"), (c_cat, "دسته مشکل")):
        text_center(box, y + head_h / 2, label, f_head, navy_txt)
    y += head_h

    mx = max(summary["تعداد تیکت"].max(), 1)
    grid = _hex("#c9d3e3")
    for i, r in enumerate(summary.itertuples(index=False)):
        cat, cnt, pct = r
        d.rectangle([x0, y, x1, y + row_h], fill=_hex("#f3f6fb") if i % 2 else "white")
        # gradient bar in the count cell, anchored to the right edge
        bar_w = int((c_cnt[1] - c_cnt[0] - 6 * S) * cnt / mx)
        for k in range(bar_w):
            t_ = k / max(bar_w, 1)
            col = tuple(int(a + (b - a) * t_) for a, b in zip(_hex("#e8f1ff"), _hex("#8fbcf5")))
            xx = c_cnt[1] - 3 * S - bar_w + k
            d.line([(xx, y + 4 * S), (xx, y + row_h - 4 * S)], fill=col)
        text_center(c_cat, y + row_h / 2, cat, f_cell, _hex("#1a1a1a"))
        text_center(c_cnt, y + row_h / 2, fa_digits(cnt), f_cell, navy)
        text_center(c_pct, y + row_h / 2, fa_digits(f"{pct:.1f}").replace(".", "٫") + "٪", f_cell, _hex("#1a1a1a"))
        d.line([(x0, y + row_h), (x1, y + row_h)], fill=grid, width=S)
        y += row_h

    total = int(summary["تعداد تیکت"].sum())
    d.rectangle([x0, y, x1, y + row_h], fill=_hex("#dbe7f9"))
    text_center(c_cat, y + row_h / 2, "جمع کل", f_bold, navy)
    text_center(c_cnt, y + row_h / 2, fa_digits(total), f_bold, navy)
    text_center(c_pct, y + row_h / 2, fa_digits("100.0").replace(".", "٫") + "٪", f_bold, navy)
    y += row_h
    # vertical grid + outer border
    for xx in (c_cat[0], c_cnt[0]):
        d.line([(xx, title_h + head_h), (xx, y)], fill=grid, width=S)
    d.rectangle([x0, title_h, x1, y], outline=grid, width=S)

    img = img.crop((0, 0, W, y + pad)).resize((W // S, (y + pad) // S), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def caption(summary: pd.DataFrame, title: str) -> str:
    lines = [title, ""]
    for r in summary.itertuples(index=False):
        lines.append(f"• {r[0]}: {fa_digits(r[1])} ({fa_digits(f'{r[2]:.1f}')}٪)")
    lines += ["", f"جمع کل: {fa_digits(int(summary['تعداد تیکت'].sum()))} تیکت"]
    return "\n".join(lines)


def build_report(data: bytes, settings: Settings, categorizer: TicketCategorizer):
    """Returns (png_bytes, caption_text, categorized_xlsx_bytes)."""
    df = clean_excel(data, settings)
    df = categorizer.categorize_df(df)
    summary = summarize(df)
    title = report_title(df)
    png = render_png(summary, title, settings)
    xbuf = io.BytesIO()
    with pd.ExcelWriter(xbuf, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name="تیکت‌ها")
        summary.rename(columns={"درصد": "درصد از کل"}).to_excel(xw, index=False, sheet_name="خلاصه")
    return png, caption(summary, title), xbuf.getvalue()
