"""Extract page text from lecture and textbook PDFs.

This module uses PyMuPDF text extraction only. OCR is intentionally not used, so
scanned/image-only pages may produce empty text and will be reported with a
warning.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union


PathLike = Union[str, Path]


class TextExtractionError(RuntimeError):
    """Raised when text cannot be extracted from a PDF."""


def extract_text_from_pdf(
    pdf_path: PathLike,
    min_text_chars: int = 10,
) -> Dict[int, str]:
    """Extract text from every page of a PDF.

    Args:
        pdf_path: Lecture or textbook PDF path.
        min_text_chars: Pages with fewer non-whitespace characters are returned
            as an empty string and reported with a warning.

    Returns:
        A dictionary mapping 1-based page numbers to extracted text.
    """
    source_pdf = Path(pdf_path)
    _validate_pdf_path(source_pdf)

    try:
        import fitz
    except ImportError as exc:
        raise TextExtractionError(
            "PyMuPDF is required for PDF text extraction. Install it with: "
            "pip install -r requirements.txt"
        ) from exc

    page_text: Dict[int, str] = {}
    try:
        with fitz.open(source_pdf) as document:
            for page_index in range(document.page_count):
                page_number = page_index + 1
                page = document.load_page(page_index)
                text = page.get_text("text").strip()

                if len("".join(text.split())) < min_text_chars:
                    warnings.warn(
                        f"Page {page_number} of {source_pdf} has little or no extractable text. "
                        "Returning an empty string. OCR is not used.",
                        stacklevel=2,
                    )
                    text = ""

                page_text[page_number] = text
    except Exception as exc:
        raise TextExtractionError(f"Could not extract text from {source_pdf}: {exc}") from exc

    return page_text


def extract_lecture_text(
    lecture_pdf: PathLike,
    notes_dir: Optional[PathLike] = None,
    save_sources: bool = False,
    min_text_chars: int = 10,
) -> Dict[int, str]:
    """Extract lecture PDF text and optionally save `page_###_source.txt` files."""
    page_text = extract_text_from_pdf(lecture_pdf, min_text_chars=min_text_chars)
    if save_sources:
        if notes_dir is None:
            raise TextExtractionError("notes_dir is required when save_sources=True.")
        save_page_text_sources(page_text, notes_dir)
    return page_text


def extract_textbook_text(
    textbook_pdf: PathLike,
    min_text_chars: int = 10,
) -> Dict[int, str]:
    """Extract text from the optional textbook PDF."""
    return extract_text_from_pdf(textbook_pdf, min_text_chars=min_text_chars)


def save_page_text_sources(page_text: Mapping[int, str], notes_dir: PathLike) -> None:
    """Save extracted lecture text as `page_001_source.txt`, etc."""
    output_dir = Path(notes_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for page_number, text in sorted(page_text.items()):
        source_path = output_dir / f"page_{page_number:03d}_source.txt"
        source_path.write_text(text, encoding="utf-8")


def extract_lecture_text_from_config(
    config: Mapping[str, Any],
    save_sources: bool = True,
    min_text_chars: int = 10,
) -> Dict[int, str]:
    """CLI-friendly helper that accepts the dictionary returned by `load_config`."""
    try:
        lecture_pdf = config["input"]["lecture_pdf"]
        notes_dir = config["output"]["notes_dir"]
    except KeyError as exc:
        raise TextExtractionError(f"Config is missing required key: {exc}") from exc

    return extract_lecture_text(
        lecture_pdf=lecture_pdf,
        notes_dir=notes_dir,
        save_sources=save_sources,
        min_text_chars=min_text_chars,
    )


def main() -> None:
    """Small command-line entry point for manual testing."""
    parser = argparse.ArgumentParser(description="Extract text from each page of a PDF.")
    parser.add_argument("pdf_path", help="Path to the lecture or textbook PDF.")
    parser.add_argument("--notes-dir", default=None, help="Directory for optional page source text files.")
    parser.add_argument("--save-sources", action="store_true", help="Save page_###_source.txt files.")
    parser.add_argument(
        "--min-text-chars",
        type=int,
        default=10,
        help="Minimum non-whitespace characters needed before a page is considered extractable.",
    )
    args = parser.parse_args()

    if args.save_sources:
        page_text = extract_lecture_text(
            lecture_pdf=args.pdf_path,
            notes_dir=args.notes_dir,
            save_sources=True,
            min_text_chars=args.min_text_chars,
        )
    else:
        page_text = extract_text_from_pdf(args.pdf_path, min_text_chars=args.min_text_chars)

    for page_number, text in sorted(page_text.items()):
        print(f"page {page_number:03d}: {len(text)} characters")


def _validate_pdf_path(pdf_path: Path) -> None:
    if not pdf_path.exists():
        raise TextExtractionError(f"PDF does not exist: {pdf_path}")
    if not pdf_path.is_file():
        raise TextExtractionError(f"PDF path is not a file: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise TextExtractionError(f"PDF must have a .pdf extension: {pdf_path}")


if __name__ == "__main__":
    main()
