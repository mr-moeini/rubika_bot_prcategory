"""Prompt-driven analysis -> categorized Excel (+ Summerty sheet), PNG summary table and chat messages."""
from __future__ import annotations

import io
from copy import copy
import re
from dataclasses import dataclass, field

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from PIL import Image, ImageDraw, ImageFont

from .categorizer import CATEGORIES, NEEDS_DECISION, TicketCategorizer, build_text
from .config import Settings
from .persian import JALALI_MONTHS, fa_digits, normalize, rtl
from .rules import check_exclusion, hard_category

_PHONE = re.compile(r"(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)")
_PACKAGE_PATH = re.compile(r"^\[6\]\s*بسته ها\s*>\s*\[6-8\]")
OUT_OF_SCOPE = "خارج از تحلیل"
F_TYPE, F_PKG, F_TEXT, F_SERVICE = "نوع مشکل تایپ", "نام بسته", "محتوای خدمات", "نوع درخواست خدمات"
NAVY = "1F3864"


@dataclass
class RowResult:
    excel_row: int
    ticket: str = ""
    package: bool = True          # row belongs to «مشکلات بسته»
    excluded: bool = False
    reason: str = ""
    rule: int = 0
    type_only: bool = False       # excluded only because of the unreliable type column
    category: str = ""
    conf: float = 1.0
    second: str = ""
    second_conf: float = 0.0
    note: str = ""                # borderline / duplicate explanation


@dataclass
class Report:
    png: bytes
    caption: str
    messages: list = field(default_factory=list)
    xlsx: bytes = b""
    summary: pd.DataFrame | None = None
    results: list = field(default_factory=list)


def _cell(v):
    return "" if v is None or (isinstance(v, float) and v != v) else str(v)


def analyze(df: pd.DataFrame, categorizer: TicketCategorizer, settings: Settings) -> list[RowResult]:
    """df row i  <->  Excel row i + 2. Implements steps 1-2 of the analysis prompt."""
    results, pending, seen = [], [], {}
    has_service = F_SERVICE in df.columns
    for i, rec in enumerate(df.to_dict("records")):
        r = RowResult(excel_row=i + 2, ticket=_cell(rec.get("شماره تیکت")))
        svc = normalize(_cell(rec.get(F_SERVICE)))
        r.package = bool(_PACKAGE_PATH.match(svc)) if has_service else True
        results.append(r)
        if not r.package:
            continue
        content, pkg, typ = _cell(rec.get(F_TEXT)), _cell(rec.get(F_PKG)), _cell(rec.get(F_TYPE))
        text = build_text(content, pkg)
        ex = check_exclusion(content, typ, has_category_hint=" hint_" in text)
        if ex:
            r.excluded = True
            r.rule, r.reason, r.type_only = ex
        else:
            hc = hard_category(content, pkg)
            if hc:
                r.category = hc
            else:
                pending.append((r, text))
        key = normalize(content)
        if len(key) > 15:
            seen.setdefault(key, []).append(r.excel_row)
    preds = categorizer.predict([t for _, t in pending])
    for (r, _), p in zip(pending, preds):
        r.category, r.conf, r.second, r.second_conf = p["label"], p["conf"], p["second"], p["second_conf"]
        if r.conf < settings.min_confidence:
            r.note = f"اطمینان پایین؛ نزدیک به «{r.category}» ({fa_digits(f'{r.conf:.0%}')}) و «{r.second}» ({fa_digits(f'{r.second_conf:.0%}')})"
            r.category = NEEDS_DECISION
        elif r.conf < settings.borderline_confidence or r.conf - r.second_conf < settings.borderline_margin:
            r.note = f"انتخاب «{r.category}» ({fa_digits(f'{r.conf:.0%}')}) ولی نزدیک به «{r.second}» ({fa_digits(f'{r.second_conf:.0%}')})"
    by_row = {r.excel_row: r for r in results}
    for rows in seen.values():
        if len(rows) > 1:
            for x in rows:
                others = "، ".join(fa_digits(y) for y in rows if y != x)
                by_row[x].note = (by_row[x].note + " | " if by_row[x].note else "") + f"تکراری با ردیف {others}"
    return results


def summarize(results: list[RowResult]) -> pd.DataFrame:
    counts = {}
    for r in results:
        if r.package and not r.excluded:
            counts[r.category] = counts.get(r.category, 0) + 1
    order = CATEGORIES + [NEEDS_DECISION]
    rows = [(c, counts[c]) for c in order if counts.get(c)]
    rows.sort(key=lambda x: (x[0] == NEEDS_DECISION, -x[1], order.index(x[0])))
    total = sum(n for _, n in rows) or 1
    return pd.DataFrame({"دسته مشکل": [c for c, _ in rows], "تعداد تیکت": [n for _, n in rows],
                         "درصد": [n * 100 / total for _, n in rows]})


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


def _path_parts(svc: str):
    parts = [re.sub(r"^\[[\d\-]+\]\s*", "", p.strip()) for p in normalize(svc).split(">")]
    return (parts[0] if parts else ""), (parts[-1] if parts else "")


def build_workbook(data: bytes, results: list[RowResult], summary: pd.DataFrame, settings: Settings) -> bytes:
    """Edits the original workbook: drops mobile column + out-of-scope rows, adds Category, adds Summerty."""
    wb = load_workbook(io.BytesIO(data))
    ws = wb.worksheets[0]
    full_mode = any(not r.package for r in results)

    # 1) mask phone numbers inside free text
    for row in ws.iter_rows(min_row=2):
        for c in row:
            if isinstance(c.value, str) and _PHONE.search(c.value):
                c.value = _PHONE.sub("[شماره حذف شد]", c.value)
    # 2) drop mobile column(s)
    drop = {normalize(x) for x in settings.drop_columns}
    for idx in sorted((c.column for c in ws[1] if normalize(c.value) in drop), reverse=True):
        ws.delete_cols(idx)
    # 3) Category (+ full-mode columns) appended at the end
    hdr = {normalize(c.value): c.column for c in ws[1] if c.value is not None}
    last = ws.max_column
    new_cols = ["Category"] + (["نوع خدمت", "زیردسته"] if full_mode else [])
    for k, name in enumerate(new_cols, start=1):
        cell = ws.cell(row=1, column=last + k, value=name)
        src = ws.cell(row=1, column=last)
        cell.font, cell.fill, cell.alignment, cell.border = copy(src.font), copy(src.fill), copy(src.alignment), copy(src.border)
        ws.column_dimensions[get_column_letter(last + k)].width = 28
    cat_col = last + 1
    svc_col = hdr.get(normalize(F_SERVICE))
    # shifted column index after deleting mobile col
    if svc_col:
        svc_col = [c.column for c in ws[1] if normalize(c.value) == normalize(F_SERVICE)][0]
    for r in results:
        if r.package:
            ws.cell(row=r.excel_row, column=cat_col, value=OUT_OF_SCOPE if r.excluded else r.category)
        if full_mode:
            svc = _cell(ws.cell(row=r.excel_row, column=svc_col).value) if svc_col else ""
            top, leaf = _path_parts(svc)
            ws.cell(row=r.excel_row, column=cat_col + 1, value=top)
            ws.cell(row=r.excel_row, column=cat_col + 2,
                    value=(OUT_OF_SCOPE if r.excluded else r.category) if r.package else leaf)
    # 4) normal mode: remove excluded rows (bottom-up so numbers stay valid)
    if not full_mode:
        for r in sorted((x for x in results if x.excluded), key=lambda x: -x.excel_row):
            ws.delete_rows(r.excel_row)

    # 5) Summerty sheet
    sm = wb.create_sheet("Summerty")
    sm.sheet_view.rightToLeft = True
    cat_letter = get_column_letter(cat_col)
    last_row = max(ws.max_row, 2)
    rng = f"'{ws.title}'!${cat_letter}$2:${cat_letter}${last_row}"
    nz = "B Nazanin"
    head_font = Font(name=nz, size=12, bold=True, color="FFFFFF")
    body_font = Font(name=nz, size=12)
    bold_font = Font(name=nz, size=12, bold=True)
    for j, h in enumerate(["دسته مشکل", "تعداد تیکت", "درصد از کل"], start=1):
        c = sm.cell(row=1, column=j, value=h)
        c.font, c.fill = head_font, PatternFill("solid", fgColor=NAVY)
        c.alignment = Alignment(horizontal="center", vertical="center")
    n = len(summary)
    tot_row = n + 2
    for i, cat in enumerate(summary["دسته مشکل"], start=2):
        sm.cell(row=i, column=1, value=cat)
        sm.cell(row=i, column=2, value=f"=COUNTIF({rng},A{i})")
        sm.cell(row=i, column=3, value=f"=IF($B${tot_row}=0,0,B{i}/$B${tot_row})").number_format = "0.0%"
        for j in (1, 2, 3):
            c = sm.cell(row=i, column=j)
            c.font = body_font
            c.alignment = Alignment(horizontal="right" if j == 1 else "center")
            if i % 2 == 1:
                c.fill = PatternFill("solid", fgColor="DCE6F1")
    sm.cell(row=tot_row, column=1, value="جمع کل")
    sm.cell(row=tot_row, column=2, value=f"=SUM(B2:B{tot_row - 1})")
    sm.cell(row=tot_row, column=3, value=f"=SUM(C2:C{tot_row - 1})").number_format = "0.0%"
    ctl = tot_row + 1
    sm.cell(row=ctl, column=1, value="کنترل (جمع جدول = تعداد تیکت‌های تحلیل‌شده شیت)")
    sm.cell(row=ctl, column=2,
            value=f'=IF(B{tot_row}=COUNTA({rng})-COUNTIF({rng},"{OUT_OF_SCOPE}"),"OK","مغایرت")')
    for rr in (tot_row, ctl):
        for j in (1, 2, 3):
            c = sm.cell(row=rr, column=j)
            c.font = bold_font
            c.alignment = Alignment(horizontal="right" if j == 1 else "center")
            if rr == tot_row:
                c.fill = PatternFill("solid", fgColor="BDD0EA")
    sm.column_dimensions["A"].width = 46
    sm.column_dimensions["B"].width = 16
    sm.column_dimensions["C"].width = 16
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _chunks(lines: list[str], limit: int = 3300) -> list[str]:
    out, cur = [], ""
    for ln in lines:
        if cur and len(cur) + len(ln) + 1 > limit:
            out.append(cur)
            cur = ""
        cur += ("\n" if cur else "") + ln
    if cur:
        out.append(cur)
    return out


def build_messages(results: list[RowResult], summary: pd.DataFrame, title: str) -> tuple[str, list[str]]:
    kept = [r for r in results if r.package and not r.excluded]
    removed = [r for r in results if r.package and r.excluded]
    lines = [title, ""]
    for r in summary.itertuples(index=False):
        lines.append(f"• {r[0]}: {fa_digits(r[1])} ({fa_digits(f'{r[2]:.1f}')}٪)")
    lines += ["", f"جمع کل: {fa_digits(len(kept))} تیکت | حذف‌شده: {fa_digits(len(removed))} تیکت"]
    caption = "\n".join(lines)

    msgs = []
    if removed:
        ls = [f"🗑 تیکت‌های حذف‌شده از تحلیل ({fa_digits(len(removed))}):"]
        for r in removed:
            extra = " (فقط بر اساس نوع مشکل؛ متن شکایت مشخص دارد)" if r.type_only else ""
            ls.append(f"• ردیف {fa_digits(r.excel_row)} | قاعده {fa_digits(r.rule)}: {r.reason}{extra}")
        msgs += _chunks(ls)
    border = [r for r in kept if r.note]
    if border:
        ls = [f"⚠️ تیکت‌های مرزی / نیازمند تصمیم / تکراری ({fa_digits(len(border))}):"]
        for r in border:
            ls.append(f"• ردیف {fa_digits(r.excel_row)} ← {r.category}: {r.note}")
        msgs += _chunks(ls)
    return caption, msgs


def build_report(data: bytes, settings: Settings, categorizer: TicketCategorizer) -> Report:
    df = pd.read_excel(io.BytesIO(data))
    df.columns = [str(c).strip() for c in df.columns]
    results = analyze(df, categorizer, settings)
    summary = summarize(results)
    title = report_title(df)
    png = render_png(summary, title, settings)
    caption, msgs = build_messages(results, summary, title)
    xlsx = build_workbook(data, results, summary, settings)
    return Report(png=png, caption=caption, messages=msgs, xlsx=xlsx, summary=summary, results=results)
