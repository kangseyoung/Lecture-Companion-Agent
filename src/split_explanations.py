"""Split per-lecture explanation markdown files into page note markdown files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Union

from src.file_matching import find_matching_explanation_in_dir
from src.generate_notes import load_gpt_explanations_by_page


PathLike = Union[str, Path]


@dataclass(frozen=True)
class SplitExplanationResult:
    lecture_pdf: Path
    explanation_file: Optional[Path]
    notes_dir: Path
    created_notes: List[Path]
    skipped_notes: List[Path]
    missing_pages: List[int]
    page_count: int


def split_explanations_for_lectures(
    lecture_pdfs: Iterable[PathLike],
    explanations_dir: PathLike,
    output_root_dir: PathLike,
    allowed_suffixes: Sequence[str],
    overwrite_existing_notes: bool = False,
) -> List[SplitExplanationResult]:
    """Split matched explanation markdown files into `page_###.md` notes.

    This function does not call OpenAI or read reference PDFs. It only reads the
    explanation markdown and writes editable note files for sections that exist.
    """
    results: List[SplitExplanationResult] = []
    explanations_root = Path(explanations_dir)
    output_root = Path(output_root_dir)

    for lecture_pdf_value in sorted((Path(path) for path in lecture_pdfs), key=lambda item: item.name.casefold()):
        lecture_pdf = lecture_pdf_value.resolve()
        lecture_stem = lecture_pdf.stem
        notes_dir = output_root / lecture_stem / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)

        explanation_file = find_matching_explanation_in_dir(
            lecture_pdf=lecture_pdf,
            explanations_dir=explanations_root,
            allowed_suffixes=allowed_suffixes,
        )
        page_count = _pdf_page_count(lecture_pdf)

        if explanation_file is None:
            results.append(
                SplitExplanationResult(
                    lecture_pdf=lecture_pdf,
                    explanation_file=None,
                    notes_dir=notes_dir,
                    created_notes=[],
                    skipped_notes=[],
                    missing_pages=list(range(1, page_count + 1)),
                    page_count=page_count,
                )
            )
            continue

        sections = load_gpt_explanations_by_page(explanation_file)
        created_notes: List[Path] = []
        skipped_notes: List[Path] = []
        missing_pages: List[int] = []

        for page_number in range(1, page_count + 1):
            section = sections.get(page_number, "").strip()
            note_path = notes_dir / f"page_{page_number:03d}.md"
            if not section:
                missing_pages.append(page_number)
                continue
            if note_path.exists() and not overwrite_existing_notes:
                skipped_notes.append(note_path)
                continue

            note_path.write_text(section.rstrip() + "\n", encoding="utf-8")
            created_notes.append(note_path)

        results.append(
            SplitExplanationResult(
                lecture_pdf=lecture_pdf,
                explanation_file=explanation_file,
                notes_dir=notes_dir,
                created_notes=created_notes,
                skipped_notes=skipped_notes,
                missing_pages=missing_pages,
                page_count=page_count,
            )
        )

    return results


def _pdf_page_count(pdf_path: Path) -> int:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF is required to count PDF pages. Install it with: pip install -r requirements.txt"
        ) from exc

    try:
        with fitz.open(pdf_path) as document:
            return max(1, document.page_count)
    except Exception as exc:
        raise RuntimeError(f"Could not read page count from {pdf_path}: {exc}") from exc
