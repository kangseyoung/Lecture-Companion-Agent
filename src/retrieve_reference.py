"""Retrieve simple textbook references for each lecture page.

This MVP uses keyword overlap rather than embeddings or a vector database. The
chunking and scoring functions are deliberately small and readable so they can
later be replaced by embedding search without changing the rest of the pipeline.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Union

try:
    from extract_text import extract_text_from_pdf
except ImportError:  # Allows package-style imports in later refactors.
    from .extract_text import extract_text_from_pdf


PathLike = Union[str, Path]
Reference = Dict[str, Any]


@dataclass(frozen=True)
class TextChunk:
    """A small searchable textbook chunk."""

    text: str
    source: str
    page: int
    keywords: Set[str]


def retrieve_references_for_pages(
    lecture_pages: Mapping[int, str],
    textbook_pdf: Optional[PathLike] = None,
    top_k: int = 3,
    chunk_size_words: int = 180,
    chunk_overlap_words: int = 40,
) -> Dict[int, List[Reference]]:
    """Find related textbook chunks for each lecture page.

    Returns:
        {
            1: [
                {"text": "related textbook chunk", "source": "textbook.pdf", "page": 23}
            ]
        }
    """
    if textbook_pdf is None:
        return {page_number: [] for page_number in lecture_pages}

    textbook_path = Path(textbook_pdf)
    if not textbook_path.exists():
        return {page_number: [] for page_number in lecture_pages}

    textbook_pages = extract_text_from_pdf(textbook_path)
    textbook_chunks = split_textbook_into_chunks(
        textbook_pages=textbook_pages,
        source=textbook_path.name,
        chunk_size_words=chunk_size_words,
        chunk_overlap_words=chunk_overlap_words,
    )
    return retrieve_references_from_textbook_pages(
        lecture_pages=lecture_pages,
        textbook_chunks=textbook_chunks,
        top_k=top_k,
    )


def retrieve_references_from_textbook_pages(
    lecture_pages: Mapping[int, str],
    textbook_chunks: Iterable[TextChunk],
    top_k: int = 3,
) -> Dict[int, List[Reference]]:
    """Find top textbook chunks for each lecture page using keyword overlap."""
    chunks = list(textbook_chunks)
    results: Dict[int, List[Reference]] = {}

    for page_number, lecture_text in sorted(lecture_pages.items()):
        if not lecture_text or not lecture_text.strip():
            results[page_number] = []
            continue

        lecture_keywords = extract_keywords(lecture_text)
        if not lecture_keywords:
            results[page_number] = []
            continue

        scored_chunks = []
        for chunk in chunks:
            overlap = lecture_keywords & chunk.keywords
            if not overlap:
                continue
            score = len(overlap)
            scored_chunks.append((score, len(chunk.keywords), chunk))

        scored_chunks.sort(key=lambda item: (item[0], item[1]), reverse=True)
        results[page_number] = [
            {
                "text": chunk.text,
                "source": chunk.source,
                "page": chunk.page,
            }
            for _, _, chunk in scored_chunks[:top_k]
        ]

    return results


def split_textbook_into_chunks(
    textbook_pages: Mapping[int, str],
    source: str = "textbook.pdf",
    chunk_size_words: int = 180,
    chunk_overlap_words: int = 40,
) -> List[TextChunk]:
    """Split textbook page text into overlapping chunks.

    The overlap reduces the chance that a relevant idea is split across two
    chunks. This simple strategy can later be replaced by semantic chunking.
    """
    if chunk_size_words <= 0:
        raise ValueError("chunk_size_words must be greater than zero.")
    if chunk_overlap_words < 0:
        raise ValueError("chunk_overlap_words cannot be negative.")
    if chunk_overlap_words >= chunk_size_words:
        raise ValueError("chunk_overlap_words must be smaller than chunk_size_words.")

    chunks: List[TextChunk] = []
    step = chunk_size_words - chunk_overlap_words

    for page_number, page_text in sorted(textbook_pages.items()):
        words = page_text.split()
        if not words:
            continue

        for start in range(0, len(words), step):
            chunk_words = words[start : start + chunk_size_words]
            if not chunk_words:
                continue
            chunk_text = " ".join(chunk_words)
            chunks.append(
                TextChunk(
                    text=chunk_text,
                    source=source,
                    page=page_number,
                    keywords=extract_keywords(chunk_text),
                )
            )
            if start + chunk_size_words >= len(words):
                break

    return chunks


def retrieve_references_from_config(
    config: Mapping[str, Any],
    lecture_pages: Mapping[int, str],
    top_k: int = 3,
) -> Dict[int, List[Reference]]:
    """CLI-friendly helper using the dictionary returned by `load_config`."""
    use_textbook = bool(config.get("generation", {}).get("use_textbook", False))
    textbook_pdf = config.get("input", {}).get("textbook_pdf")
    if not use_textbook or not textbook_pdf:
        return {page_number: [] for page_number in lecture_pages}

    return retrieve_references_for_pages(
        lecture_pages=lecture_pages,
        textbook_pdf=textbook_pdf,
        top_k=top_k,
    )


def retrieve_reference_context(page_text: str, textbook_text: Mapping[int, str], top_k: int = 3) -> List[Reference]:
    """Compatibility helper for retrieving references for a single lecture page."""
    if not page_text or not page_text.strip():
        return []
    chunks = split_textbook_into_chunks(textbook_text)
    return retrieve_references_from_textbook_pages({1: page_text}, chunks, top_k=top_k)[1]


def extract_keywords(text: str) -> Set[str]:
    """Extract simple English/Korean keyword tokens for overlap scoring."""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[가-힣]{2,}", text.lower())
    return {token for token in tokens if token not in _STOPWORDS}


def main() -> None:
    """Small command-line entry point for manual testing."""
    parser = argparse.ArgumentParser(description="Retrieve textbook references for lecture pages.")
    parser.add_argument("lecture_pdf", help="Path to the lecture PDF.")
    parser.add_argument("--textbook", default=None, help="Optional textbook PDF path.")
    parser.add_argument("--top-k", type=int, default=3, help="Number of chunks per lecture page.")
    args = parser.parse_args()

    lecture_pages = extract_text_from_pdf(args.lecture_pdf)
    references = retrieve_references_for_pages(
        lecture_pages=lecture_pages,
        textbook_pdf=args.textbook,
        top_k=args.top_k,
    )
    for page_number, items in sorted(references.items()):
        print(f"lecture page {page_number:03d}: {len(items)} reference chunks")
        for item in items:
            preview = item["text"][:100].replace("\n", " ")
            print(f"  - {item['source']} page {item['page']}: {preview}")


_STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "this",
    "with",
    "from",
    "into",
    "are",
    "was",
    "were",
    "will",
    "can",
    "could",
    "should",
    "then",
    "than",
    "have",
    "has",
    "had",
    "using",
    "used",
    "use",
    "page",
    "chapter",
    "section",
}


if __name__ == "__main__":
    main()
