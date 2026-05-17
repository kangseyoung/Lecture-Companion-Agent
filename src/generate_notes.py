"""Generate Korean explanatory study notes as editable markdown files.

The notes are designed for beginner understanding. They are not exam summaries,
memorization sheets, or presentation scripts. Each note is grounded in the
lecture page text, related textbook chunks, and optional user notes.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union


PathLike = Union[str, Path]
Reference = Dict[str, Any]


SYSTEM_PROMPT = """You write Korean explanatory study notes for complete beginners.

Rules:
- Write in Korean.
- Do not invent information that is not supported by the lecture text, textbook references, or user notes.
- Do not create exam tips.
- Do not create memorization points.
- Do not create presentation summaries or scripts.
- If the lecture text is incomplete or sparse, explicitly say that the page text is limited.
- Keep technical terms understandable.
- Use clear paragraphs and bullet points when helpful.
"""


class NoteGenerationError(RuntimeError):
    """Raised when notes cannot be generated."""


def generate_notes_for_pages(
    lecture_pages: Mapping[int, str],
    references_by_page: Mapping[int, List[Reference]],
    user_notes_by_page: Mapping[int, str],
    notes_dir: PathLike,
    model_name: str = "gpt-4.1-mini",
    overwrite_existing_notes: bool = False,
    gpt_explanations_by_page: Optional[Mapping[int, str]] = None,
) -> List[Path]:
    """Generate or reuse markdown notes for every lecture page.

    Returns paths for all page markdown files, including skipped existing files.
    """
    output_dir = Path(notes_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    markdown_paths: List[Path] = []
    pages_to_generate: List[int] = []
    for page_number in sorted(lecture_pages):
        note_path = output_dir / _note_filename(page_number)
        markdown_paths.append(note_path)
        if note_path.exists() and not overwrite_existing_notes:
            continue
        pages_to_generate.append(page_number)

    if not pages_to_generate:
        return markdown_paths

    gpt_explanations = gpt_explanations_by_page or {}
    client = _openai_client()
    for page_number in pages_to_generate:
        prompt = build_note_prompt(
            page_number=page_number,
            lecture_text=lecture_pages.get(page_number, ""),
            references=references_by_page.get(page_number, []),
            user_note=user_notes_by_page.get(page_number, user_notes_by_page.get(0, "")),
            gpt_explanation=gpt_explanations.get(page_number, ""),
        )
        markdown = _generate_markdown(client=client, model_name=model_name, prompt=prompt)
        markdown = _ensure_gpt_explanation_preserved(markdown, gpt_explanations.get(page_number, ""))
        note_path = output_dir / _note_filename(page_number)
        note_path.write_text(_normalize_markdown(markdown), encoding="utf-8")

    return markdown_paths


def generate_page_notes(
    page_number: int,
    lecture_text: str,
    references: Optional[List[Reference]] = None,
    user_note: str = "",
    gpt_explanation: str = "",
    notes_dir: PathLike = "output/notes",
    model_name: str = "gpt-4.1-mini",
    overwrite_existing_notes: bool = False,
) -> Path:
    """Generate or reuse one page note and return its markdown path."""
    paths = generate_notes_for_pages(
        lecture_pages={page_number: lecture_text},
        references_by_page={page_number: references or []},
        user_notes_by_page={page_number: user_note} if user_note else {},
        notes_dir=notes_dir,
        model_name=model_name,
        overwrite_existing_notes=overwrite_existing_notes,
        gpt_explanations_by_page={page_number: gpt_explanation} if gpt_explanation else {},
    )
    return paths[0]


def generate_notes_from_config(
    config: Mapping[str, Any],
    lecture_pages: Mapping[int, str],
    references_by_page: Mapping[int, List[Reference]],
) -> List[Path]:
    """CLI-friendly helper using the dictionary returned by `load_config`."""
    try:
        notes_dir = config["output"]["notes_dir"]
        model_name = config["model"]["model_name"]
        overwrite = config["generation"]["overwrite_existing_notes"]
    except KeyError as exc:
        raise NoteGenerationError(f"Config is missing required key: {exc}") from exc

    user_notes_by_page: Dict[int, str] = {}
    user_notes_path = config.get("input", {}).get("user_notes")
    if config.get("generation", {}).get("use_user_notes") and user_notes_path:
        user_notes_by_page = load_user_notes_by_page(user_notes_path)

    gpt_explanations_by_page: Dict[int, str] = {}
    gpt_explanations_path = config.get("input", {}).get("gpt_explanations")
    if gpt_explanations_path:
        gpt_explanations_by_page = load_gpt_explanations_by_page(
            gpt_explanations_path,
            page_numbers=lecture_pages.keys(),
        )

    return generate_notes_for_pages(
        lecture_pages=lecture_pages,
        references_by_page=references_by_page,
        user_notes_by_page=user_notes_by_page,
        notes_dir=notes_dir,
        model_name=model_name,
        overwrite_existing_notes=overwrite,
        gpt_explanations_by_page=gpt_explanations_by_page,
    )


def load_user_notes_by_page(user_notes_path: PathLike) -> Dict[int, str]:
    """Load optional user notes and split them by page markers when present.

    Supported page headings include `# Page 1`, `## page_001`, `페이지 1`,
    and `[page 1]`. If no marker exists, the whole file is returned under key
    `0` as global notes.
    """
    path = Path(user_notes_path)
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}

    marker_pattern = re.compile(
        r"^\s{0,3}(?:#{1,6}\s*)?(?:\[?\s*(?:page|페이지)\s*_?0*(\d+)\s*\]?)",
        re.IGNORECASE,
    )
    notes_by_page: Dict[int, List[str]] = {}
    current_page: Optional[int] = None
    found_marker = False

    for line in text.splitlines():
        marker = marker_pattern.match(line)
        if marker:
            current_page = int(marker.group(1))
            notes_by_page.setdefault(current_page, [])
            found_marker = True
            continue
        if current_page is not None:
            notes_by_page.setdefault(current_page, []).append(line)

    if not found_marker:
        return {0: text}

    return {
        page_number: "\n".join(lines).strip()
        for page_number, lines in notes_by_page.items()
        if "\n".join(lines).strip()
    }


def load_gpt_explanations_by_page(
    gpt_explanations_path: PathLike = "input/gpt_explanations.md",
    page_numbers: Optional[Iterable[int]] = None,
) -> Dict[int, str]:
    """Parse one markdown file containing explanations separated by headings.

    Supported headings include `# Slide 1`, `## slide 1`, `# Page 1`,
    `# 페이지 1`, and `## 슬라이드 1`. Text before the first matching heading is
    ignored. Markdown inside each section is preserved except for trimming
    leading and trailing blank lines.
    """
    path = Path(gpt_explanations_path)
    requested_pages = list(page_numbers) if page_numbers is not None else None
    if not path.exists():
        return {page_number: "" for page_number in requested_pages} if requested_pages else {}

    text = path.read_text(encoding="utf-8")
    sections = _split_gpt_explanations_markdown(text)
    if requested_pages is None:
        return sections

    return {page_number: sections.get(page_number, "") for page_number in requested_pages}


def _split_gpt_explanations_markdown(markdown: str) -> Dict[int, str]:
    heading_pattern = re.compile(
        r"^\s{0,3}#{1,6}\s*(?:slide|page|페이지|슬라이드)\s+(\d+)\s*$",
        re.IGNORECASE,
    )
    sections: Dict[int, List[str]] = {}
    current_page: Optional[int] = None
    in_code_block = False

    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            if current_page is not None:
                sections.setdefault(current_page, []).append(line)
            in_code_block = not in_code_block
            continue

        if not in_code_block:
            match = heading_pattern.match(line)
            if match:
                current_page = int(match.group(1))
                sections.setdefault(current_page, [])
                continue

        if current_page is not None:
            sections.setdefault(current_page, []).append(line)

    return {
        page_number: "\n".join(lines).strip()
        for page_number, lines in sections.items()
    }


def build_note_prompt(
    page_number: int,
    lecture_text: str,
    references: List[Reference],
    user_note: str,
    gpt_explanation: str = "",
) -> str:
    """Build the grounded Korean note-generation prompt."""
    reference_text = _format_references(references)
    gpt_explanation_text = gpt_explanation.strip() if gpt_explanation and gpt_explanation.strip() else "(없음)"
    user_note_text = user_note.strip() if user_note and user_note.strip() else "(없음)"
    lecture_text_value = (
        lecture_text.strip()
        if lecture_text and lecture_text.strip()
        else "(추출 가능한 페이지 텍스트가 거의 없거나 없습니다.)"
    )

    return f"""Generate Korean explanatory markdown notes for lecture page {page_number}.

Use this markdown structure:

## 원문 해석
Translate the lecture page naturally into Korean.
Do not translate word-by-word if it sounds awkward.
Keep technical terms understandable.

## 교재 참고 설명
Explain the concept using the related textbook content.
Mention the textbook page number if available.
If no textbook reference is provided, write:
"첨부된 교재 참고 내용이 없습니다."

## 아주 쉬운 설명
Explain the idea for a complete beginner.
Assume the reader has no background knowledge.
Use simple analogies.
Explain step by step.
Do not make the explanation childish.
Do not distort the concept.

## 자세한 설명
If a matching GPT explanation is provided, place the useful markdown content here.
Preserve the user's provided markdown as much as possible.
Do not heavily rewrite it.
Only lightly clean formatting if necessary.
If no matching GPT explanation is provided, omit this section or write a concise beginner-friendly explanation supported by the lecture and textbook.

## 내가 추가한 설명
Include the relevant user note if provided.
If there is no user note, leave this section empty.

Hard rules:
- Do not invent unsupported information.
- If the lecture text is incomplete, say that the page text is limited.
- Do not create exam tips.
- Do not create memorization points.
- Do not create presentation summaries.
- Write in Korean.
- Use clear paragraphs and bullet points when helpful.
- Source priority is: 1) original lecture PDF text, 2) textbook PDF references, 3) GPT explanations markdown, 4) user notes.
- Treat GPT explanations as additional context, not as higher authority than the lecture or textbook.
- Preserve useful markdown formatting from GPT explanations, including bullet points, code blocks, math expressions, and tables.

[Lecture page text]
{lecture_text_value}

[Related textbook chunks]
{reference_text}

[Matching GPT explanation markdown]
{gpt_explanation_text}

[User note for this page]
{user_note_text}
"""


def _openai_client():
    if not os.getenv("OPENAI_API_KEY"):
        raise NoteGenerationError(
            "OPENAI_API_KEY is not set. Set it before generating notes, or keep existing "
            "markdown files and run later rendering steps."
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise NoteGenerationError(
            "The openai package is required for note generation. Install it with: "
            "pip install -r requirements.txt"
        ) from exc

    return OpenAI()


def _generate_markdown(client: Any, model_name: str, prompt: str) -> str:
    response = client.responses.create(
        model=model_name,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return response.output_text


def _format_references(references: List[Reference]) -> str:
    if not references:
        return "(없음)"

    formatted = []
    for index, item in enumerate(references, start=1):
        source = item.get("source", "textbook.pdf")
        page = item.get("page", "unknown")
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        formatted.append(f"[{index}] {source}, page {page}\n{text}")

    return "\n\n".join(formatted) if formatted else "(없음)"


def _normalize_markdown(markdown: str) -> str:
    return markdown.strip() + "\n"


def _ensure_gpt_explanation_preserved(markdown: str, gpt_explanation: str) -> str:
    explanation = gpt_explanation.strip() if gpt_explanation else ""
    if not explanation:
        return markdown
    if explanation in markdown:
        return markdown
    if "## 자세한 설명" in markdown:
        return markdown.rstrip() + "\n\n" + explanation + "\n"
    return markdown.rstrip() + "\n\n## 자세한 설명\n\n" + explanation + "\n"


def _note_filename(page_number: int) -> str:
    return f"page_{page_number:03d}.md"


def main() -> None:
    """Small command-line entry point for manual testing one page."""
    parser = argparse.ArgumentParser(description="Generate a Korean explanation note for one page.")
    parser.add_argument("--page", type=int, required=True, help="Lecture page number.")
    parser.add_argument("--lecture-text-file", required=True, help="Text file containing lecture page text.")
    parser.add_argument("--notes-dir", default="output/notes", help="Directory for generated markdown notes.")
    parser.add_argument("--model", default="gpt-4.1-mini", help="OpenAI model name.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing page markdown file.")
    args = parser.parse_args()

    lecture_text = Path(args.lecture_text_file).read_text(encoding="utf-8")
    note_path = generate_page_notes(
        page_number=args.page,
        lecture_text=lecture_text,
        notes_dir=args.notes_dir,
        model_name=args.model,
        overwrite_existing_notes=args.force,
    )
    print(note_path)


if __name__ == "__main__":
    main()
