"""Helpers for matching lecture PDFs to explanation markdown files."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Union


PathLike = Union[str, Path]


def find_matching_explanation_file(
    lecture_pdf: PathLike,
    explanation_files: Iterable[PathLike],
    allowed_suffixes: Sequence[str],
) -> Optional[Path]:
    """Return the best explanation markdown file for one lecture PDF.

    Matching rules:
    - exact stem match
    - explanation stem starts with lecture stem
    - explanation stem contains lecture stem

    Ranking rules:
    - exact stem match first
    - then configured suffix matches
    - then most recently modified file, with a warning if this decides
    """
    lecture_path = Path(lecture_pdf)
    lecture_stem = lecture_path.stem
    candidates = [
        Path(path)
        for path in explanation_files
        if _stem_matches(lecture_stem, Path(path).stem)
    ]
    if not candidates:
        return None

    exact_matches = [
        path for path in candidates
        if _normalize(path.stem) == _normalize(lecture_stem)
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        return _choose_most_recent_with_warning(lecture_path, exact_matches)

    suffix_matches = [
        path for path in candidates
        if _has_configured_suffix(lecture_stem, path.stem, allowed_suffixes)
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    if len(suffix_matches) > 1:
        return _choose_most_recent_with_warning(lecture_path, suffix_matches)

    if len(candidates) == 1:
        return candidates[0]
    return _choose_most_recent_with_warning(lecture_path, candidates)


def find_matching_explanation_in_dir(
    lecture_pdf: PathLike,
    explanations_dir: PathLike,
    allowed_suffixes: Sequence[str],
) -> Optional[Path]:
    """Find the best matching markdown explanation in a directory.

    Priority:
    1. `{explanations_dir}/{lecture_stem}/explanation.md`
    2. `{explanations_dir}/{lecture_stem}.md`
    3. `{explanations_dir}/{lecture_stem}_explanation.md`
    4. `{explanations_dir}/{lecture_stem}_notes.md`
    5. Existing loose matching rules
    """
    directory = Path(explanations_dir)
    if not directory.exists() or not directory.is_dir():
        return None

    lecture_stem = Path(lecture_pdf).stem
    folder_explanation = directory / lecture_stem / "explanation.md"
    if folder_explanation.exists() and folder_explanation.is_file():
        return folder_explanation

    exact_file = directory / f"{lecture_stem}.md"
    if exact_file.exists() and exact_file.is_file():
        return exact_file

    explanation_file = directory / f"{lecture_stem}_explanation.md"
    if explanation_file.exists() and explanation_file.is_file():
        return explanation_file

    notes_file = directory / f"{lecture_stem}_notes.md"
    if notes_file.exists() and notes_file.is_file():
        return notes_file

    files = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in {".md", ".markdown"}
    )
    return find_matching_explanation_file(lecture_pdf, files, allowed_suffixes)


def match_explanations_for_lectures(
    lecture_pdfs: Iterable[PathLike],
    explanation_files: Iterable[PathLike],
    allowed_suffixes: Sequence[str],
) -> dict:
    """Return `{lecture_pdf_path: matching_explanation_or_none}`."""
    files = list(explanation_files)
    return {
        Path(lecture_pdf): find_matching_explanation_file(
            lecture_pdf=lecture_pdf,
            explanation_files=files,
            allowed_suffixes=allowed_suffixes,
        )
        for lecture_pdf in lecture_pdfs
    }


def _stem_matches(lecture_stem: str, explanation_stem: str) -> bool:
    lecture = _normalize(lecture_stem)
    explanation = _normalize(explanation_stem)
    return explanation == lecture or explanation.startswith(lecture) or lecture in explanation


def _has_configured_suffix(
    lecture_stem: str,
    explanation_stem: str,
    allowed_suffixes: Sequence[str],
) -> bool:
    lecture = _normalize(lecture_stem)
    explanation = _normalize(explanation_stem)
    for suffix in allowed_suffixes:
        normalized_suffix = _normalize(suffix)
        if explanation == lecture + normalized_suffix:
            return True
        if explanation.endswith(normalized_suffix) and lecture in explanation:
            return True
    return False


def _choose_most_recent_with_warning(lecture_pdf: Path, candidates: List[Path]) -> Path:
    candidates = sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)
    chosen = candidates[0]
    print(
        "Warning: multiple explanation files match "
        f"{lecture_pdf.name}. Using most recently modified file: {chosen.name}"
    )
    return chosen


def _normalize(value: str) -> str:
    return value.casefold()
