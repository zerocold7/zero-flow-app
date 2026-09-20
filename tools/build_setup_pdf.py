"""Rebuild docs/Zero-Flow-Setup-Guide.pdf from docs/SETUP-CPU-LAPTOP.md.

Run it after editing the beginner guide, so the printable PDF never drifts from the
Markdown it comes from:

    pip install reportlab
    python tools/build_setup_pdf.py            # writes docs/Zero-Flow-Setup-Guide.pdf
    python tools/build_setup_pdf.py other.pdf  # or somewhere else, to preview first

Needs Windows' Arial and Consolas: ReportLab's built-in fonts cannot draw the arrows
and dashes the guide uses. See tools/README.md.
"""
import os
import re
import sys
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (ListFlowable, ListItem, Paragraph,
                                Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "docs", "SETUP-CPU-LAPTOP.md")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "docs", "Zero-Flow-Setup-Guide.pdf")
FOOTER = "Zero- Flow Engine — Laptop Setup Guide"

# Arial / Consolas rather than the built-in Helvetica / Courier: the built-ins cannot
# draw "→" and friends, and the guide uses them.
FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
for name, file in (("Arial", "arial.ttf"), ("Arial-Bold", "arialbd.ttf"),
                   ("Arial-Italic", "ariali.ttf"), ("Consolas", "consola.ttf"),
                   ("Consolas-Bold", "consolab.ttf")):
    pdfmetrics.registerFont(TTFont(name, os.path.join(FONTS, file)))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic")

INK, GREEN, GREY = colors.HexColor("#1B1F24"), colors.HexColor("#2F6F4F"), colors.HexColor("#5B636C")
CODE_INK, CODE_BG, CODE_RULE = colors.HexColor("#10222E"), colors.HexColor("#F3F4F6"), colors.HexColor("#D5D9DE")
TIP_BG, WARN_BG, WARN = colors.HexColor("#EAF4EE"), colors.HexColor("#FBEEE6"), colors.HexColor("#B4532A")

body = ParagraphStyle("body", fontName="Arial", fontSize=10, leading=14.5, textColor=INK,
                      spaceAfter=5, alignment=TA_LEFT)
S = {
    "title": ParagraphStyle("title", parent=body, fontName="Arial-Bold", fontSize=24, leading=28, spaceAfter=2),
    "subtitle": ParagraphStyle("subtitle", parent=body, fontName="Arial-Bold", fontSize=13, leading=17,
                               textColor=GREEN, spaceAfter=3),
    "meta": ParagraphStyle("meta", parent=body, fontSize=8, leading=11, textColor=GREY, spaceAfter=10),
    "h2": ParagraphStyle("h2", parent=body, fontName="Arial-Bold", fontSize=15, leading=19,
                         textColor=GREEN, spaceBefore=12, spaceAfter=6, keepWithNext=1),
    "h3": ParagraphStyle("h3", parent=body, fontName="Arial-Bold", fontSize=11.5, leading=15,
                         textColor=GREEN, spaceBefore=8, spaceAfter=4, keepWithNext=1),
    "box": ParagraphStyle("box", parent=body, spaceAfter=0),
    "cell": ParagraphStyle("cell", parent=body, fontSize=9, leading=12.5, spaceAfter=0),
    "head": ParagraphStyle("head", parent=body, fontName="Arial-Bold", fontSize=9, leading=12.5,
                           textColor=colors.white, spaceAfter=0),
    "code": ParagraphStyle("code", fontName="Consolas", fontSize=9, leading=12, textColor=CODE_INK),
}
WIDTH = A4[0] - 2 * 18 * mm

EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\uFE0F]")
# Blockquote callouts: leading emoji → the label and colours the printed guide uses.
CALLOUTS = {"💡": ("TIP", GREEN, TIP_BG), "⚠️": ("IMPORTANT", WARN, WARN_BG),
            "⌨️": ("IMPORTANT", WARN, WARN_BG), "🐢": ("NOTE", GREEN, TIP_BG),
            "🔒": ("PRIVACY", GREEN, TIP_BG), "🎮": ("NOTE", GREEN, TIP_BG)}


def inline(text):
    """Markdown inline → ReportLab markup: **bold**, `code`, [links](...)."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = EMOJI.sub("", text).strip()
    # Hold code spans aside first, so bold can wrap them ("**`Fn + Esc`**").
    codes = []
    text = re.sub(r"`([^`]*)`", lambda m: codes.append(m.group(1)) or f"\x00{len(codes) - 1}\x00", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(text))
    return re.sub("\x00(\\d+)\x00", lambda m: (
        f'<font name="Consolas" color="#10222E" backColor="#F3F4F6">'
        f'{escape(codes[int(m.group(1))])}</font>'), text)


def boxed(flowable, border, fill, pad=7):
    t = Table([[flowable]], colWidths=[WIDTH])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, border), ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("LEFTPADDING", (0, 0), (-1, -1), pad + 2), ("RIGHTPADDING", (0, 0), (-1, -1), pad + 2),
        ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
    ]))
    return t


def callout(text):
    for emoji, (label, border, fill) in CALLOUTS.items():
        if text.startswith(emoji[0]):
            hex_ = border.hexval()[2:]
            para = Paragraph(f'<font color="#{hex_}"><b>{label}</b></font>&nbsp;&nbsp;{inline(text)}', S["box"])
            return [Spacer(1, 3), boxed(para, border, fill), Spacer(1, 7)]
    return [Paragraph(inline(text), body)]


def code(lines):
    pre = Preformatted("\n".join(lines), S["code"])
    return [Spacer(1, 2), boxed(pre, CODE_RULE, CODE_BG, pad=6), Spacer(1, 7)]


def table(rows):
    first = 0.30 if len(rows[0][0]) < 20 else 0.34
    widths = [WIDTH * first, WIDTH * (1 - first)]
    data = [[Paragraph(inline(c), S["head" if r == 0 else "cell"]) for c in row]
            for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9F8")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5DCD8")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#C9D6CF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [Spacer(1, 2), t, Spacer(1, 8)]


def items(lines, numbered):
    flow = [ListItem(Paragraph(inline(l), body), leftIndent=16) for l in lines]
    kw = dict(bulletType="1", start=numbered, bulletFontName="Arial-Bold", bulletColor=GREEN,
              bulletFontSize=10) if numbered else dict(bulletType="bullet", start="•",
              bulletColor=GREEN, bulletFontSize=9)
    return [ListFlowable(flow, leftIndent=16, **kw)]


# ------------------------------------------------------------------ the markdown
lines = open(SRC, encoding="utf-8").read().splitlines()
story = [
    Paragraph("Zero- Flow Engine", S["title"]),
    Paragraph("Beginner Setup Guide — Laptop / CPU Mode (no NVIDIA GPU)", S["subtitle"]),
    Paragraph("Windows 11 · CPU mode, no graphics card needed · github.com/zerocold7/local-voice-flow",
              S["meta"]),
]
i = 0
while i < len(lines):
    t = lines[i].strip()
    if not t or t == "---" or t.startswith("# "):
        i += 1
        continue
    if t.startswith("```"):
        block = []
        i += 1
        while i < len(lines) and not lines[i].strip().startswith("```"):
            block.append(lines[i])
            i += 1
        story += code(block)
    elif t.startswith("## "):
        story.append(Paragraph(inline(t[3:]), S["h2"]))
    elif t.startswith("### "):
        story.append(Paragraph(inline(t[4:]), S["h3"]))
    elif t.startswith(">"):
        quote = t.lstrip("> ").strip()
        if quote and not quote.startswith(("📄", "🌍")):     # links to this PDF / the Arabic guide
            story += callout(quote)
    elif t.startswith("|"):
        rows = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            if not all(re.fullmatch(r"-+", c) for c in cells):
                rows.append(cells)
            i += 1
        story += table(rows)
        continue
    elif t.startswith("- ") or re.match(r"\d+\. ", t):
        numbered = re.match(r"(\d+)\. ", t)
        group = []
        while i < len(lines) and (lines[i].strip().startswith("- ") if not numbered
                                  else re.match(r"\d+\. ", lines[i].strip())):
            item = re.sub(r"^(- |\d+\. )", "", lines[i].strip())
            if re.search(r"[\u0600-\u06FF]", item):
                # ReportLab cannot shape Arabic; point at the Arabic guide instead.
                item = ("In Arabic: every command has an Arabic equivalent — they are listed "
                        "in the Arabic guide (SETUP-CPU-LAPTOP.ar.md) and in CONFIGURATION.md.")
            group.append(item)
            i += 1
        story += items(group, int(numbered.group(1)) if numbered else 0)
        continue
    else:
        story.append(Paragraph(inline(t), body))
    i += 1


def footer(canvas, doc):
    canvas.saveState()
    y = 12 * mm
    canvas.setStrokeColor(colors.HexColor("#C9D6CF"))
    canvas.setLineWidth(0.6)
    canvas.line(18 * mm, y + 9, A4[0] - 18 * mm, y + 9)
    canvas.setFont("Arial", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(18 * mm, y, FOOTER)
    canvas.drawRightString(A4[0] - 18 * mm, y, f"Page {doc.page}")
    canvas.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                        topMargin=16 * mm, bottomMargin=22 * mm,
                        title="Zero- Flow Engine - Laptop Setup Guide", author="zerocold7",
                        subject="Beginner setup guide, generated from docs/SETUP-CPU-LAPTOP.md")
doc.build(story, onFirstPage=footer, onLaterPages=footer)

# Every character must exist in the embedded fonts, or it prints as an empty box.
arial = pdfmetrics.getFont("Arial").face.charToGlyph
text = open(SRC, encoding="utf-8").read()
missing = sorted({c for c in EMOJI.sub("", text) if ord(c) > 127 and ord(c) not in arial
                  and not ("\u0600" <= c <= "\u06FF")})
print(f"wrote {OUT}; pages built; characters missing from Arial: {missing or 'none'}")
