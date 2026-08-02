#!/usr/bin/env python3
"""Render docs/whitepaper.md to a stable, self-contained Chinese PDF."""

from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase import pdfmetrics, ttfonts
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/whitepaper.md"
OUTPUT = ROOT / "output/pdf/PDF转Markdown-技术白皮书.pdf"


def inline(value: str, font_name: str = "STSong-Light") -> str:
    value = html.escape(value, quote=False)
    value = re.sub(r"`([^`]+)`", rf"<font name='{font_name}'>\1</font>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    return value


def build() -> Path:
    font_name = "STSong-Light"
    # Prefer an embedded macOS CJK font so Poppler and other readers do not
    # depend on an external Adobe-GB1 language pack.
    for candidate in (Path("/System/Library/Fonts/Hiragino Sans GB.ttc"), Path("/System/Library/Fonts/STHeiti Medium.ttc")):
        if candidate.is_file():
            try:
                pdfmetrics.registerFont(ttfonts.TTFont("PDF2MDCJK", str(candidate), subfontIndex=0))
                font_name = "PDF2MDCJK"
                break
            except Exception:
                continue
    if font_name == "STSong-Light":
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleCN", parent=styles["Title"], fontName=font_name, fontSize=22, leading=30, alignment=TA_CENTER, spaceAfter=16)
    h1 = ParagraphStyle("H1CN", parent=styles["Heading1"], fontName=font_name, fontSize=16, leading=24, spaceBefore=12, spaceAfter=8)
    h2 = ParagraphStyle("H2CN", parent=styles["Heading2"], fontName=font_name, fontSize=13, leading=20, spaceBefore=8, spaceAfter=5)
    body = ParagraphStyle("BodyCN", parent=styles["BodyText"], fontName=font_name, fontSize=10.5, leading=18, firstLineIndent=21, spaceAfter=7)
    meta = ParagraphStyle("MetaCN", parent=body, fontSize=9, textColor="#555555", firstLineIndent=0)
    story = []
    for raw in SOURCE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        if line.startswith(">"):
            story.append(Paragraph(inline(line[1:].strip(), font_name), meta))
        elif line.startswith("## "):
            story.append(Paragraph(inline(line[3:], font_name), h1))
        elif line.startswith("### "):
            story.append(Paragraph(inline(line[4:], font_name), h2))
        elif line.startswith("# "):
            story.append(Paragraph(inline(line[2:], font_name), title))
        elif line.startswith("- "):
            story.append(Paragraph("• " + inline(line[2:], font_name), body))
        else:
            story.append(Paragraph(inline(line, font_name), body))
        story.append(Spacer(1, 1.5 * mm))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title="PDF 转 Markdown 技术白皮书")
    doc.build(story)
    print(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    build()
