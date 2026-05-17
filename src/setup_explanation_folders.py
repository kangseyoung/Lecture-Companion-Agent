"""Create per-lecture explanation markdown folders and templates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Union


PathLike = Union[str, Path]


@dataclass(frozen=True)
class ExplanationTemplateResult:
    lecture_pdf: Path
    explanation_dir: Path
    explanation_file: Path
    page_count: int
    created: bool


def create_explanation_folders_for_lectures(
    lectures_dir: PathLike,
    explanations_dir: PathLike,
) -> List[ExplanationTemplateResult]:
    """Create `input/explanations/{lecture_stem}/explanation.md` for each PDF.

    Existing `explanation.md` files are never overwritten.
    """
    lecture_paths = _lecture_pdfs_in_dir(lectures_dir)
    return create_explanation_folders_for_pdfs(lecture_paths, explanations_dir)


def create_explanation_folders_for_pdfs(
    lecture_pdfs: Iterable[PathLike],
    explanations_dir: PathLike,
) -> List[ExplanationTemplateResult]:
    """Create explanation folders/templates for explicit lecture PDF paths."""
    output_root = Path(explanations_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    results: List[ExplanationTemplateResult] = []
    for lecture_pdf in sorted((Path(path) for path in lecture_pdfs), key=lambda item: item.name.casefold()):
        if lecture_pdf.suffix.lower() != ".pdf":
            continue
        lecture_stem = lecture_pdf.stem
        explanation_dir = output_root / lecture_stem
        explanation_file = explanation_dir / "explanation.md"
        explanation_dir.mkdir(parents=True, exist_ok=True)

        page_count = _pdf_page_count(lecture_pdf)
        created = False
        if not explanation_file.exists():
            explanation_file.write_text(_template_markdown(page_count), encoding="utf-8")
            created = True

        results.append(
            ExplanationTemplateResult(
                lecture_pdf=lecture_pdf,
                explanation_dir=explanation_dir,
                explanation_file=explanation_file,
                page_count=page_count,
                created=created,
            )
        )
    return results


def _lecture_pdfs_in_dir(lectures_dir: PathLike) -> List[Path]:
    directory = Path(lectures_dir)
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted(
        path.resolve()
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


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


def _template_markdown(page_count: int) -> str:
    sections = []
    for page_number in range(1, page_count + 1):
        sections.append(
            f"# Slide {page_number}\n\n"
            f"여기에 {page_number}번 슬라이드 설명을 붙여넣으세요.\n"
        )
    return "\n".join(sections).rstrip() + "\n"
