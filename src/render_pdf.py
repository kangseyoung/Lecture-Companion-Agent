"""Render the final annotated PDF with page images and Korean markdown notes.

The renderer reads already-created page PNG files and editable markdown notes.
It does not read or modify the original lecture PDF.
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union


PathLike = Union[str, Path]


@dataclass(frozen=True)
class TextBlock:
    """A parsed markdown text block ready for PDF layout."""

    text: str
    style: str


class PdfRenderError(RuntimeError):
    """Raised when the annotated PDF cannot be rendered."""


def render_annotated_pdf(
    page_images: Optional[Sequence[PathLike]] = None,
    notes_dir: PathLike = "output/notes",
    output_pdf: PathLike = "output/final/annotated_explanation.pdf",
    pages_dir: Optional[PathLike] = None,
    font_path: Optional[PathLike] = None,
    page_size: str = "A4_landscape",
    left_width_ratio: float = 0.52,
    right_width_ratio: float = 0.48,
    margin: float = 24,
) -> Path:
    """Create the annotated PDF.

    Args:
        page_images: Optional explicit page image paths. If omitted, images are
            read from `pages_dir`.
        notes_dir: Directory containing `page_001.md`, `page_002.md`, etc.
        output_pdf: Final PDF path.
        pages_dir: Directory containing rendered page images.
        font_path: Optional Korean TTF/TTC font path. If omitted, common Windows
            Korean fonts are searched, then `KOREAN_FONT_PATH` is checked.
        page_size: Currently supports `A4_landscape`.
        left_width_ratio: Relative width of the original page image area.
        right_width_ratio: Relative width of the note panel area.
        margin: Page margin in points.

    Returns:
        The final PDF path.
    """
    _validate_layout(left_width_ratio, right_width_ratio, margin)
    image_paths = _resolve_page_images(page_images, pages_dir)
    if not image_paths:
        raise PdfRenderError("No page images found. Expected files like output/pages/page_001.png.")

    notes_path = Path(notes_dir)
    if not notes_path.exists():
        raise PdfRenderError(f"Notes directory does not exist: {notes_path}")

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise PdfRenderError(
            "ReportLab is required for PDF rendering. Install it with: "
            "pip install -r requirements.txt"
        ) from exc

    font_name = _register_korean_font(font_path, pdfmetrics, TTFont)
    if font_name is None:
        font_name = "Helvetica"
        print(
            "Warning: Korean font was not found. Korean text may not render correctly. "
            "Set KOREAN_FONT_PATH or pass font_path."
        )

    if page_size != "A4_landscape":
        raise PdfRenderError(f"Unsupported layout.page_size '{page_size}'. Supported value: A4_landscape.")

    width, height = landscape(A4)
    output_path = Path(output_pdf)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(str(output_path), pagesize=(width, height))
    content_width = width - (2 * margin)
    gap = 16
    left_width = (content_width - gap) * left_width_ratio
    right_width = (content_width - gap) * right_width_ratio
    image_rect = (margin, margin, left_width, height - (2 * margin))
    note_rect = (margin + left_width + gap, margin, right_width, height - (2 * margin))

    for image_path in image_paths:
        page_number = _page_number_from_image(image_path)
        note_file = notes_path / f"page_{page_number:03d}.md"
        markdown = _read_note_markdown(note_file)
        text_pages = _paginate_markdown(markdown, note_rect[2], note_rect[3], font_name, pdfmetrics)

        for page_index, blocks in enumerate(text_pages, start=1):
            _draw_page_image(pdf, ImageReader, image_path, image_rect)
            _draw_note_panel(pdf, colors, note_rect)
            _draw_note_blocks(
                pdf=pdf,
                blocks=blocks,
                rect=note_rect,
                font_name=font_name,
                page_number=page_number,
                continuation_index=page_index,
                continuation_total=len(text_pages),
            )
            pdf.showPage()

    pdf.save()
    return output_path


def render_from_config(config: Mapping[str, Any], font_path: Optional[PathLike] = None) -> Path:
    """CLI-friendly helper using the dictionary returned by `load_config`."""
    layout = config.get("layout", {})
    return render_annotated_pdf(
        pages_dir=config["output"]["pages_dir"],
        notes_dir=config["output"]["notes_dir"],
        output_pdf=config["output"]["final_pdf"],
        font_path=font_path,
        page_size=layout.get("page_size", "A4_landscape"),
        left_width_ratio=float(layout.get("left_width_ratio", 0.52)),
        right_width_ratio=float(layout.get("right_width_ratio", 0.48)),
        margin=float(layout.get("margin", 24)),
    )


def main() -> None:
    """Small command-line entry point for manual rendering."""
    parser = argparse.ArgumentParser(description="Render the final annotated explanation PDF.")
    parser.add_argument("--pages-dir", default="output/pages", help="Directory containing page_###.png files.")
    parser.add_argument("--notes-dir", default="output/notes", help="Directory containing page_###.md files.")
    parser.add_argument(
        "--output",
        default="output/final/annotated_explanation.pdf",
        help="Final annotated PDF path.",
    )
    parser.add_argument("--font-path", default=None, help="Optional Korean TTF/TTC font path.")
    args = parser.parse_args()

    output_path = render_annotated_pdf(
        pages_dir=args.pages_dir,
        notes_dir=args.notes_dir,
        output_pdf=args.output,
        font_path=args.font_path,
    )
    print(output_path)


def _resolve_page_images(
    page_images: Optional[Sequence[PathLike]],
    pages_dir: Optional[PathLike],
) -> List[Path]:
    if page_images is not None:
        resolved = [Path(path) for path in page_images]
    else:
        directory = Path(pages_dir or "output/pages")
        if not directory.exists():
            raise PdfRenderError(f"Pages directory does not exist: {directory}")
        resolved = sorted(directory.glob("page_*.png"))

    missing = [path for path in resolved if not path.exists()]
    if missing:
        raise PdfRenderError(f"Page image does not exist: {missing[0]}")

    return sorted(resolved, key=_page_number_from_image)


def _page_number_from_image(image_path: Path) -> int:
    match = re.search(r"page_(\d+)\.png$", image_path.name, re.IGNORECASE)
    if not match:
        raise PdfRenderError(f"Page image filename must look like page_001.png: {image_path}")
    return int(match.group(1))


def _read_note_markdown(note_file: Path) -> str:
    if not note_file.exists():
        return "## 원문 해석\n\n이 페이지에 대한 markdown 노트가 없습니다."
    return note_file.read_text(encoding="utf-8-sig")


def _parse_markdown(markdown: str) -> List[TextBlock]:
    blocks: List[TextBlock] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            blocks.append(TextBlock("", "blank"))
            continue
        if line.startswith("## "):
            blocks.append(TextBlock(line[3:].strip(), "heading"))
        elif line.startswith("# "):
            blocks.append(TextBlock(line[2:].strip(), "heading"))
        elif line.startswith(("- ", "* ")):
            blocks.append(TextBlock("- " + line[2:].strip(), "bullet"))
        else:
            blocks.append(TextBlock(line, "paragraph"))
    return blocks


def _paginate_markdown(markdown: str, panel_width: float, panel_height: float, font_name: str, pdfmetrics) -> List[List[TextBlock]]:
    blocks = _parse_markdown(markdown)
    usable_width = panel_width - 28
    usable_height = panel_height - 42
    pages: List[List[TextBlock]] = []
    current: List[TextBlock] = []
    used_height = 0.0

    for block in blocks:
        wrapped = _wrap_block(block, usable_width, font_name, pdfmetrics)
        for wrapped_block in wrapped:
            block_height = _line_height(wrapped_block.style)
            if current and used_height + block_height > usable_height:
                pages.append(current)
                current = []
                used_height = 0.0
            current.append(wrapped_block)
            used_height += block_height

    if current:
        pages.append(current)
    return pages or [[TextBlock("", "blank")]]


def _wrap_block(block: TextBlock, width: float, font_name: str, pdfmetrics) -> List[TextBlock]:
    if block.style == "blank":
        return [block]

    font_size = _font_size(block.style)
    words = block.text.split()
    if not words:
        return [block]

    prefix = ""
    continuation_prefix = ""
    if block.style == "bullet" and block.text.startswith("- "):
        words = block.text[2:].split()
        prefix = "- "
        continuation_prefix = "  "

    lines: List[TextBlock] = []
    current = prefix
    for word in words:
        candidate = f"{current} {word}".strip() if current.strip() else prefix + word
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= width:
            current = candidate
            continue
        if current.strip():
            lines.append(TextBlock(current, block.style))
            current = continuation_prefix
        else:
            current = prefix

        if pdfmetrics.stringWidth(current + word, font_name, font_size) <= width:
            current = current + word
            continue

        pieces = _split_long_word(word, width, font_name, font_size, pdfmetrics)
        for piece in pieces[:-1]:
            lines.append(TextBlock((current + piece).strip(), block.style))
            current = continuation_prefix
        current = continuation_prefix + pieces[-1] if continuation_prefix else pieces[-1]

    if current.strip():
        lines.append(TextBlock(current, block.style))

    return lines or [block]


def _split_long_word(word: str, width: float, font_name: str, font_size: float, pdfmetrics) -> List[str]:
    pieces: List[str] = []
    current = ""
    for char in word:
        candidate = current + char
        if current and pdfmetrics.stringWidth(candidate, font_name, font_size) > width:
            pieces.append(current)
            current = char
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces or [word]


def _draw_page_image(pdf, ImageReader, image_path: Path, rect: tuple) -> None:
    x, y, width, height = rect
    image = ImageReader(str(image_path))
    image_width, image_height = image.getSize()
    scale = min(width / image_width, height / image_height)
    draw_width = image_width * scale
    draw_height = image_height * scale
    draw_x = x + (width - draw_width) / 2
    draw_y = y + (height - draw_height) / 2
    pdf.drawImage(image, draw_x, draw_y, width=draw_width, height=draw_height, preserveAspectRatio=True)


def _draw_note_panel(pdf, colors, rect: tuple) -> None:
    x, y, width, height = rect
    pdf.setFillColor(colors.HexColor("#fbfbf8"))
    pdf.setStrokeColor(colors.HexColor("#d8d8d0"))
    pdf.roundRect(x, y, width, height, radius=6, stroke=1, fill=1)


def _draw_note_blocks(
    pdf,
    blocks: Iterable[TextBlock],
    rect: tuple,
    font_name: str,
    page_number: int,
    continuation_index: int,
    continuation_total: int,
) -> None:
    x, y, width, height = rect
    cursor_y = y + height - 22
    text_x = x + 14

    pdf.setFont(font_name, 8)
    pdf.setFillColorRGB(0.42, 0.42, 0.42)
    label = f"Page {page_number:03d}"
    if continuation_total > 1:
        label += f" ({continuation_index}/{continuation_total})"
    pdf.drawString(text_x, cursor_y, label)
    cursor_y -= 18

    for block in blocks:
        size = _font_size(block.style)
        cursor_y -= _line_height(block.style)
        if block.style == "heading":
            pdf.setFillColorRGB(0.05, 0.17, 0.28)
        else:
            pdf.setFillColorRGB(0.12, 0.12, 0.12)
        pdf.setFont(font_name, size)
        if block.text:
            pdf.drawString(text_x, cursor_y, block.text)


def _font_size(style: str) -> float:
    if style == "heading":
        return 13
    return 9.5


def _line_height(style: str) -> float:
    if style == "heading":
        return 18
    if style == "blank":
        return 8
    return 13


def _register_korean_font(font_path: Optional[PathLike], pdfmetrics, TTFont) -> Optional[str]:
    path = _find_korean_font(font_path)
    if path is None:
        return None
    try:
        pdfmetrics.registerFont(TTFont("KoreanFont", str(path)))
    except Exception as exc:
        raise PdfRenderError(f"Could not register Korean font {path}: {exc}") from exc
    return "KoreanFont"


def _find_korean_font(font_path: Optional[PathLike]) -> Optional[Path]:
    candidates = []
    if font_path:
        candidates.append(Path(font_path))
    env_font = os.getenv("KOREAN_FONT_PATH")
    if env_font:
        candidates.append(Path(env_font))
    candidates.extend(
        [
            Path("C:/Windows/Fonts/malgun.ttf"),
            Path("C:/Windows/Fonts/malgunbd.ttf"),
            Path("C:/Windows/Fonts/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
            Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
        ]
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _validate_layout(left_ratio: float, right_ratio: float, margin: float) -> None:
    if left_ratio <= 0 or right_ratio <= 0:
        raise PdfRenderError("left_width_ratio and right_width_ratio must be positive.")
    if abs((left_ratio + right_ratio) - 1.0) > 0.001:
        raise PdfRenderError("left_width_ratio and right_width_ratio must add up to 1.0.")
    if margin < 0:
        raise PdfRenderError("margin cannot be negative.")


if __name__ == "__main__":
    main()
