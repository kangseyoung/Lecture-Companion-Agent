"""Convert lecture PDF pages into unchanged PNG page images.

This module reads the lecture PDF with PyMuPDF and writes one PNG per page into
the configured pages directory. The original PDF is opened read-only and is never
modified.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Union


PathLike = Union[str, Path]


@dataclass(frozen=True)
class PageImage:
    """Metadata for one rendered page image."""

    page_number: int
    path: Path
    rendered: bool


class PdfRenderError(RuntimeError):
    """Raised when a PDF cannot be rendered into page images."""


def convert_pdf_to_images(
    pdf_path: PathLike,
    pages_dir: PathLike,
    force: bool = False,
    dpi: int = 160,
) -> List[PageImage]:
    """Convert each PDF page to `page_001.png`, `page_002.png`, etc.

    Args:
        pdf_path: Path to the lecture PDF.
        pages_dir: Directory where page PNG files will be saved.
        force: Re-render pages even when the target PNG already exists.
        dpi: Render resolution. Higher values create larger, sharper images.

    Returns:
        A list of `PageImage` objects containing page numbers and image paths.
    """
    source_pdf = Path(pdf_path)
    output_dir = Path(pages_dir)
    _validate_pdf_path(source_pdf)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import fitz
    except ImportError as exc:
        raise PdfRenderError(
            "PyMuPDF is required for PDF rendering. Install it with: "
            "pip install -r requirements.txt"
        ) from exc

    rendered_pages: List[PageImage] = []
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    try:
        with fitz.open(source_pdf) as document:
            for page_index in range(document.page_count):
                page_number = page_index + 1
                image_path = output_dir / f"page_{page_number:03d}.png"

                if image_path.exists() and not force:
                    rendered_pages.append(
                        PageImage(page_number=page_number, path=image_path, rendered=False)
                    )
                    continue

                page = document.load_page(page_index)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                pixmap.save(image_path)
                rendered_pages.append(
                    PageImage(page_number=page_number, path=image_path, rendered=True)
                )
    except Exception as exc:
        raise PdfRenderError(f"Could not render PDF pages from {source_pdf}: {exc}") from exc

    return rendered_pages


def convert_from_config(config: Mapping[str, Any], force: bool = False, dpi: int = 160) -> List[PageImage]:
    """CLI-friendly helper that accepts the dictionary returned by `load_config`."""
    try:
        pdf_path = config["input"]["lecture_pdf"]
        pages_dir = config["output"]["pages_dir"]
    except KeyError as exc:
        raise PdfRenderError(f"Config is missing required key: {exc}") from exc

    return convert_pdf_to_images(pdf_path=pdf_path, pages_dir=pages_dir, force=force, dpi=dpi)


def page_images_as_dicts(page_images: List[PageImage]) -> List[Dict[str, Any]]:
    """Return plain dictionaries for callers that prefer serializable results."""
    return [
        {
            "page_number": item.page_number,
            "path": item.path,
            "rendered": item.rendered,
        }
        for item in page_images
    ]


def main() -> None:
    """Small command-line entry point for manual testing."""
    parser = argparse.ArgumentParser(description="Render a lecture PDF into page PNG images.")
    parser.add_argument("pdf_path", help="Path to the lecture PDF.")
    parser.add_argument("--pages-dir", default="output/pages", help="Directory for PNG page images.")
    parser.add_argument("--force", action="store_true", help="Re-render images that already exist.")
    parser.add_argument("--dpi", type=int, default=160, help="Render resolution.")
    args = parser.parse_args()

    page_images = convert_pdf_to_images(
        pdf_path=args.pdf_path,
        pages_dir=args.pages_dir,
        force=args.force,
        dpi=args.dpi,
    )
    for page_image in page_images:
        status = "rendered" if page_image.rendered else "skipped"
        print(f"page {page_image.page_number:03d}: {status} -> {page_image.path}")


def _validate_pdf_path(pdf_path: Path) -> None:
    if not pdf_path.exists():
        raise PdfRenderError(f"Lecture PDF does not exist: {pdf_path}")
    if not pdf_path.is_file():
        raise PdfRenderError(f"Lecture PDF path is not a file: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise PdfRenderError(f"Lecture PDF must have a .pdf extension: {pdf_path}")


if __name__ == "__main__":
    main()
