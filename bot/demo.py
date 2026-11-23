"""Render a report from a local Excel file: python -m bot.demo file.xlsx [out_dir]"""
import sys
from pathlib import Path

from .categorizer import TicketCategorizer
from .config import Settings
from .report import build_report

if __name__ == "__main__":
    src = Path(sys.argv[1])
    out = Path(sys.argv[2] if len(sys.argv) > 2 else ".")
    out.mkdir(parents=True, exist_ok=True)
    png, cap, xlsx = build_report(src.read_bytes(), Settings(), TicketCategorizer())
    (out / "ticket_categories.png").write_bytes(png)
    (out / "categorized.xlsx").write_bytes(xlsx)
    (out / "caption.txt").write_text(cap, encoding="utf-8")
    print(cap)
