"""A4 landscape material schedule, laid out like a door/window schedule.

Materials run across as columns and their attributes down as rows, with a swatch
at the top of each column where an elevation drawing would sit. That is the form
an architect already reads, and it puts the visual identification of a material
next to its numbers instead of in a separate legend.

Rendered server-side rather than in the browser because the tables are in
Chinese: a client-side PDF needs a CJK font embedded in the bundle, which costs
several megabytes on every page load, while here the system font is already on
disk and only the glyphs actually used get embedded in the file.
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PAGE = landscape(A4)
MARGIN = 13 * mm
LABEL_W = 26 * mm
# Two bands stacked per sheet, the way a door/window schedule fills its sheet
# with a D-series band above a W-series band, rather than leaving the lower half
# of every page blank.
COLS_PER_BAND = 7
BANDS_PER_PAGE = 2

# Drawing-sheet convention: black line work on white, no fills. The material
# swatch is the only thing on the sheet carrying colour, so it reads as the
# sample it is rather than as one more piece of table decoration.
INK = colors.black
MUTED = colors.black
ACCENT = colors.black
RULE = colors.black
HAIRLINE = colors.black

_FONT_CANDIDATES = [
    ("Matboard", "msjh.ttc", 0),      # Microsoft JhengHei
    ("Matboard", "msyh.ttc", 0),      # Microsoft YaHei
    ("Matboard", "mingliu.ttc", 0),
    ("Matboard", "simsun.ttc", 0),
    ("Matboard", "kaiu.ttf", None),
]
_BOLD_CANDIDATES = [
    ("Matboard-Bold", "msjhbd.ttc", 0),
    ("Matboard-Bold", "msyhbd.ttc", 0),
]

_registered: tuple[str, str] | None = None


def _fonts() -> tuple[str, str]:
    """(regular, bold) font names, registering them on first use."""
    global _registered
    if _registered:
        return _registered

    fonts_dir = Path(r"C:\Windows\Fonts")
    regular = None
    for name, filename, index in _FONT_CANDIDATES:
        path = fonts_dir / filename
        if not path.is_file():
            continue
        try:
            font = (
                TTFont(name, str(path), subfontIndex=index)
                if index is not None
                else TTFont(name, str(path))
            )
            pdfmetrics.registerFont(font)
            regular = name
            break
        except Exception:  # noqa: BLE001 - try the next candidate
            continue
    if regular is None:
        regular = "Helvetica"  # Latin fallback; layout holds, Chinese will not

    bold = regular
    for name, filename, index in _BOLD_CANDIDATES:
        path = fonts_dir / filename
        if not path.is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=index))
            bold = name
            break
        except Exception:  # noqa: BLE001
            continue
    if bold == regular and regular == "Helvetica":
        bold = "Helvetica-Bold"

    _registered = (regular, bold)
    return _registered


def _num(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}"


def _material_category(material: dict) -> str:
    for entries in (material.get("attrs") or {}).values():
        value = (entries or {}).get("Category")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _swatch(material: dict, assets_dir: Path | None, size: float):
    """The column's identifying image: the real texture, else its flat colour."""
    texture = material.get("texture")
    if texture and assets_dir:
        path = assets_dir / texture.replace("/", "\\")
        if path.is_file():
            try:
                img = Image(str(path), width=size, height=size)
                img.hAlign = "CENTER"
                return img
            except Exception:  # noqa: BLE001 - fall through to a colour chip
                pass

    drawing = Drawing(size, size)
    drawing.add(
        Rect(
            0, 0, size, size,
            fillColor=colors.HexColor(material.get("colorHex", "#C8C8C8")),
            strokeColor=HAIRLINE,
            strokeWidth=0.5,
        )
    )
    drawing.hAlign = "CENTER"
    return drawing


def build_report(
    doc: dict,
    *,
    project_name: str,
    site: str = "",
    excluded: set[int] | None = None,
    net: bool = False,
    assets_dir: Path | None = None,
) -> bytes:
    excluded = excluded or set()
    regular, bold = _fonts()
    has_overlaps = bool(doc.get("overlaps", {}).get("pairCount"))
    if not has_overlaps:
        net = False

    # Totals and the surface-type split, on the chosen basis.
    removed = 0.0
    included_regions = 0
    per_material_categories: dict[int, dict[str, float]] = {}
    for r in doc["regions"]:
        a = r["exposedAreaM2"] if net else r["areaM2"]
        cats = per_material_categories.setdefault(r["materialId"], {})
        cats[r["categoryLabel"]] = cats.get(r["categoryLabel"], 0.0) + a
        if r["materialId"] in excluded:
            removed += a
            continue
        included_regions += 1

    S = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=14, leading=18, textColor=INK),
        "meta": ParagraphStyle("m", fontName=regular, fontSize=8, leading=11.5, textColor=MUTED),
        "h2": ParagraphStyle("h", fontName=bold, fontSize=9.5, leading=13, textColor=ACCENT,
                             spaceBefore=8, spaceAfter=4),
        "rowlab": ParagraphStyle("rl", fontName=regular, fontSize=7.5, leading=10,
                                 textColor=MUTED),
        "cell": ParagraphStyle("c", fontName=regular, fontSize=7.5, leading=10,
                               textColor=INK, alignment=TA_CENTER),
        "cellName": ParagraphStyle("cn", fontName=bold, fontSize=8, leading=11,
                                   textColor=INK, alignment=TA_CENTER),
        "cellSmall": ParagraphStyle("cs", fontName=regular, fontSize=6.8, leading=9,
                                    textColor=MUTED, alignment=TA_CENTER),
        "cellNum": ParagraphStyle("cnum", fontName=regular, fontSize=8, leading=11,
                                  textColor=INK, alignment=TA_CENTER),
        "cellNumOn": ParagraphStyle("cnon", fontName=bold, fontSize=8.5, leading=11.5,
                                    textColor=ACCENT, alignment=TA_CENTER),
        "tag": ParagraphStyle("tg", fontName=bold, fontSize=8.5, leading=11,
                              textColor=INK, alignment=TA_CENTER),
        "sumCell": ParagraphStyle("sc", fontName=regular, fontSize=8, leading=11, textColor=INK),
        "sumNum": ParagraphStyle("sn", fontName=regular, fontSize=8, leading=11,
                                 textColor=INK, alignment=TA_RIGHT),
        "note": ParagraphStyle("n", fontName=regular, fontSize=7, leading=10.5,
                               textColor=MUTED, spaceBefore=2),
    }

    story: list = []

    # --- title block -------------------------------------------------------
    basis = (
        "扣除重複表面（貼合面、薄板背面、重複幾何）" if net
        else "全部面（模型中所有面的表面積）"
    )
    meta = [f"專案：{project_name}"]
    if site.strip():
        meta.append(f"基地：{site.strip()}")
    meta.append(f"計算基準：<b>{basis}</b>")
    meta.append(f"產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}")

    header = Table(
        [[Paragraph("建材彙整表", S["title"]), Paragraph("　·　".join(meta), S["meta"])]],
        colWidths=[46 * mm, PAGE[0] - 2 * MARGIN - 46 * mm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, RULE),
    ]))
    story.append(header)

    if excluded:
        names = [
            doc["materials"][mid]["name"]
            for mid in sorted(excluded)
            if mid < len(doc["materials"])
        ]
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            f"已排除不計入合計的材質（{len(names)} 項，共 {_num(removed)} m²）：{'、'.join(names)}",
            S["note"],
        ))
    story.append(Spacer(1, 3 * mm))

    # --- the schedule ------------------------------------------------------
    rows_spec = [
        "材質圖示",
        "材質名稱",
        "材質類別",
        "貼圖單元",
        "主要用於",
        "區塊數",
        "全部面 (m²)",
    ]
    if has_overlaps:
        rows_spec.append("扣除重疊 (m²)")

    # Excluded materials are left off the schedule entirely - a row of numbers
    # that is not in the total is only there to be misread. The note above the
    # table still records what was taken out and how much it came to.
    materials = [m for m in doc["summary"]["byMaterial"] if m["materialId"] not in excluded]
    col_w = (PAGE[0] - 2 * MARGIN - LABEL_W) / COLS_PER_BAND
    swatch_size = min(col_w - 12 * mm, 15 * mm)

    for band, start in enumerate(range(0, len(materials), COLS_PER_BAND)):
        chunk = materials[start:start + COLS_PER_BAND]
        if band and band % BANDS_PER_PAGE == 0:
            story.append(PageBreak())
        elif band:
            story.append(Spacer(1, 4 * mm))

        grid: list[list] = []

        tag_row = [Paragraph("編號", S["rowlab"])]
        for i, row in enumerate(chunk):
            tag_row.append(Paragraph(f"M{start + i + 1:02d}", S["tag"]))
        grid.append(tag_row)

        for label in rows_spec:
            cells = [Paragraph(label, S["rowlab"])]
            for row in chunk:
                mid = row["materialId"]
                material = doc["materials"][mid]
                if label == "材質圖示":
                    cells.append(_swatch(material, assets_dir, swatch_size))
                elif label == "材質名稱":
                    cells.append(Paragraph(row["name"], S["cellName"]))
                elif label == "材質類別":
                    cells.append(Paragraph(_material_category(material) or "—", S["cellSmall"]))
                elif label == "貼圖單元":
                    size = material.get("textureSizeM")
                    text = (
                        f"{_num(size[0] * 1000, 0)} × {_num(size[1] * 1000, 0)} mm"
                        if size else "—"
                    )
                    opacity = material.get("opacity", 1.0)
                    if opacity < 0.99:
                        text += f"<br/>透明度 {opacity * 100:.0f}%"
                    cells.append(Paragraph(text, S["cellSmall"]))
                elif label == "主要用於":
                    cats = per_material_categories.get(mid, {})
                    top = max(cats.items(), key=lambda kv: kv[1])[0] if cats else "—"
                    cells.append(Paragraph(top, S["cell"]))
                elif label == "區塊數":
                    cells.append(Paragraph(str(row["regionCount"]), S["cellNum"]))
                elif label == "全部面 (m²)":
                    cells.append(Paragraph(
                        _num(row["areaM2"]), S["cellNum"] if net else S["cellNumOn"]))
                else:  # 扣除重疊 (m²)
                    cells.append(Paragraph(
                        _num(row["exposedAreaM2"]), S["cellNumOn"] if net else S["cellNum"]))
            grid.append(cells)

        # Pad a short last page so the grid keeps its full width.
        if len(chunk) < COLS_PER_BAND:
            for r in grid:
                r.extend([""] * (COLS_PER_BAND - len(chunk)))

        heights = [6 * mm, swatch_size + 3 * mm] + [None] * (len(rows_spec) - 1)
        table = Table(grid, colWidths=[LABEL_W] + [col_w] * COLS_PER_BAND, rowHeights=heights)

        style = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 1.8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.4, HAIRLINE),
            ("BOX", (0, 0), (-1, -1), 1.0, RULE),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, RULE),
            ("LINEBELOW", (0, 1), (-1, 1), 0.8, RULE),
            ("LINEAFTER", (0, 0), (0, -1), 0.8, RULE),
        ]
        table.setStyle(TableStyle(style))
        # A band split across a page boundary loses its lower rows to the next
        # sheet, orphaned from the column headings that identify them.
        story.append(KeepTogether(table))

    # --- totals ------------------------------------------------------------
    story.append(Spacer(1, 4 * mm))

    gross_total = sum(r["areaM2"] for r in doc["regions"] if r["materialId"] not in excluded)
    net_total = sum(
        r["exposedAreaM2"] for r in doc["regions"] if r["materialId"] not in excluded
    )
    total_rows = [[
        Paragraph("<b>合計（計入者）</b>", S["sumCell"]),
        Paragraph(f"{included_regions} 區塊", S["sumNum"]),
        Paragraph(f"全部面 {_num(gross_total)} m²", S["sumNum"]),
    ]]
    widths = [46 * mm, 28 * mm, 44 * mm]
    if has_overlaps:
        total_rows[0].append(Paragraph(f"<b>扣除重疊 {_num(net_total)} m²</b>", S["sumNum"]))
        widths.append(48 * mm)
    # Fill the sheet width so the block reads as a footer rule, not a stray box.
    widths.append(PAGE[0] - 2 * MARGIN - sum(widths))
    total_rows[0].append(Paragraph("", S["sumCell"]))
    totals = Table(total_rows, colWidths=widths)
    totals.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.8, RULE),
    ]))

    story.append(totals)

    # --- render ------------------------------------------------------------
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(
        buffer, pagesize=PAGE,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=11 * mm, bottomMargin=13 * mm,
        title=f"建材彙整表 - {project_name}", author="Matboard",
    )

    def decorate(canvas, document):
        canvas.saveState()
        canvas.setFont(regular, 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 7.5 * mm, f"建材彙整表 · {project_name}")
        canvas.drawRightString(PAGE[0] - MARGIN, 7.5 * mm, f"第 {document.page} 頁")
        canvas.setStrokeColor(HAIRLINE)
        canvas.setLineWidth(0.4)
        canvas.line(MARGIN, 10 * mm, PAGE[0] - MARGIN, 10 * mm)
        canvas.restoreState()

    pdf.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()
