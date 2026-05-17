"""Command-line entry point for batch PDF explanation generation."""

from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.create_sample_pdf import create_sample_pdf
from src.config import ConfigError, load_config
from src.extract_text import extract_lecture_text, extract_textbook_text
from src.file_matching import find_matching_explanation_in_dir
from src.generate_notes import generate_notes_for_pages, load_gpt_explanations_by_page
from src.pdf_to_images import convert_pdf_to_images
from src.render_pdf import render_from_config
from src.retrieve_reference import (
    Reference,
    TextChunk,
    retrieve_references_from_textbook_pages,
    split_textbook_into_chunks,
)
from src.setup_explanation_folders import create_explanation_folders_for_lectures
from src.split_explanations import split_explanations_for_lectures


def main() -> None:
    args = _parse_args()

    if args.render_only and args.notes_only:
        _fail("--render-only and --notes-only cannot be used together.")
    if args.lecture and args.all:
        _fail("--lecture and --all cannot be used together.")
    if args.split_explanations and (args.render_only or args.notes_only or args.setup_explanations):
        _fail("--split-explanations cannot be combined with --render-only, --notes-only, or --setup-explanations.")

    try:
        config = load_config(args.config)
        if args.overwrite_notes:
            config["generation"]["overwrite_existing_notes"] = True

        if args.setup_explanations:
            _setup_explanations(config)
            return

        lecture_pdfs = _select_lecture_pdfs(config, args)
        if not lecture_pdfs:
            _fail(
                f"No lecture PDFs found in {config['input']['lectures_dir']}. "
                "Put .pdf files there, pass --lecture path\\to\\file.pdf, or run --test-sample."
            )

        if args.split_explanations:
            _split_explanations(config, lecture_pdfs)
            return

        print(f"Loaded config: {args.config}")
        print(f"Lectures to process: {len(lecture_pdfs)}")

        print("Loading reference PDFs once...")
        reference_chunks = _load_reference_chunks(config)
        print(f"Reference chunks ready: {len(reference_chunks)}")

        for index, lecture_pdf in enumerate(lecture_pdfs, start=1):
            print("")
            print(f"Processing lecture {index}/{len(lecture_pdfs)}: {lecture_pdf.name}")
            lecture_config = _config_for_lecture(config, lecture_pdf)
            _process_lecture(
                config=lecture_config,
                reference_chunks=reference_chunks,
                force_images=args.force_images,
                render_only=args.render_only,
                notes_only=args.notes_only,
            )

        print("")
        print("Done.")
    except (ConfigError, Exception) as exc:
        _fail(str(exc))


def _select_lecture_pdfs(config: Dict[str, Any], args: argparse.Namespace) -> List[Path]:
    if args.test_sample:
        sample_pdf = create_sample_pdf(config["input"]["lectures_dir"] / "sample_lecture.pdf")
        print(f"[test] Created sample PDF: {sample_pdf}")
        return [sample_pdf]

    if args.lecture:
        lecture_path = Path(args.lecture)
        if not lecture_path.is_absolute():
            lecture_path = (Path.cwd() / lecture_path).resolve()
        if not lecture_path.exists():
            _fail(f"Lecture PDF does not exist: {lecture_path}")
        if lecture_path.suffix.lower() != ".pdf":
            _fail(f"--lecture must point to a .pdf file: {lecture_path}")
        return [lecture_path]

    # Default to all configured lectures. The --all flag makes this explicit,
    # but keeping it as the default is friendlier for normal batch use.
    return list(config["input"].get("lecture_pdfs", []))


def _config_for_lecture(config: Dict[str, Any], lecture_pdf: Path) -> Dict[str, Any]:
    lecture_config = deepcopy(config)
    lecture_stem = lecture_pdf.stem
    lecture_root = config["output"]["root_dir"] / lecture_stem
    pages_dir = lecture_root / "pages"
    notes_dir = lecture_root / "notes"
    final_pdf = lecture_root / "final" / "annotated_explanation.pdf"

    pages_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)
    final_pdf.parent.mkdir(parents=True, exist_ok=True)

    lecture_config["input"]["lecture_pdf"] = lecture_pdf
    lecture_config["output"]["lecture_root"] = lecture_root
    lecture_config["output"]["pages_dir"] = pages_dir
    lecture_config["output"]["notes_dir"] = notes_dir
    lecture_config["output"]["final_pdf"] = final_pdf
    return lecture_config


def _process_lecture(
    config: Dict[str, Any],
    reference_chunks: List[TextChunk],
    force_images: bool,
    render_only: bool,
    notes_only: bool,
) -> None:
    lecture_pdf = config["input"]["lecture_pdf"]
    explanation_file = _matching_explanation_for_current_lecture(config)
    if explanation_file:
        print(f"Matched explanation file: {explanation_file.name}")
    else:
        print("Matched explanation file: none")

    print("  Converting pages to images...")
    page_images = convert_pdf_to_images(
        pdf_path=lecture_pdf,
        pages_dir=config["output"]["pages_dir"],
        force=force_images,
    )
    rendered_count = sum(1 for item in page_images if item.rendered)
    skipped_count = len(page_images) - rendered_count
    print(f"  Page images: {len(page_images)} ({rendered_count} rendered, {skipped_count} skipped)")

    if render_only:
        print("  Render-only mode: skipping note generation.")
        final_pdf = render_from_config(config)
        print(f"Saved final PDF: {_display_path(final_pdf)}")
        return

    print("  Extracting lecture text...")
    lecture_pages = extract_lecture_text(
        lecture_pdf=lecture_pdf,
        notes_dir=config["output"]["notes_dir"],
        save_sources=True,
    )
    print(f"  Lecture pages extracted: {len(lecture_pages)}")

    print("  Retrieving references...")
    references_by_page = _references_for_lecture(config, lecture_pages, reference_chunks)
    reference_count = sum(len(items) for items in references_by_page.values())
    print(f"  Related reference chunks: {reference_count}")

    print("  Loading explanation markdown...")
    gpt_explanations_by_page = _load_gpt_explanations(explanation_file, lecture_pages)
    matched_gpt_count = len([text for text in gpt_explanations_by_page.values() if text.strip()])
    print(f"  Explanation sections matched: {matched_gpt_count}")

    print("  Generating or reusing markdown notes...")
    note_paths = generate_notes_for_pages(
        lecture_pages=lecture_pages,
        references_by_page=references_by_page,
        user_notes_by_page={},
        notes_dir=config["output"]["notes_dir"],
        model_name=config["model"]["model_name"],
        overwrite_existing_notes=config["generation"]["overwrite_existing_notes"],
        gpt_explanations_by_page=gpt_explanations_by_page,
    )
    print(f"  Markdown notes ready: {len(note_paths)}")

    if notes_only:
        print(f"  Notes-only mode: skipped rendering. Notes: {_display_path(config['output']['notes_dir'])}")
        return

    print("  Rendering final PDF...")
    final_pdf = render_from_config(config)
    print(f"Saved final PDF: {_display_path(final_pdf)}")


def _load_reference_chunks(config: Dict[str, Any]) -> List[TextChunk]:
    if not config["generation"].get("use_references", config["generation"].get("use_textbook", False)):
        print("  References disabled in config.")
        return []

    reference_pdfs = config["input"].get("reference_pdfs")
    if reference_pdfs is None:
        textbook_pdf = config["input"].get("textbook_pdf")
        reference_pdfs = [textbook_pdf] if textbook_pdf else []

    chunks: List[TextChunk] = []
    for reference_pdf in reference_pdfs:
        print(f"  Loading reference: {Path(reference_pdf).name}")
        reference_pages = extract_textbook_text(reference_pdf)
        chunks.extend(
            split_textbook_into_chunks(
                textbook_pages=reference_pages,
                source=Path(reference_pdf).name,
            )
        )
    return chunks


def _references_for_lecture(
    config: Dict[str, Any],
    lecture_pages: Dict[int, str],
    reference_chunks: List[TextChunk],
) -> Dict[int, List[Reference]]:
    if not config["generation"].get("use_references", config["generation"].get("use_textbook", False)):
        return {page_number: [] for page_number in lecture_pages}
    if not reference_chunks:
        return {page_number: [] for page_number in lecture_pages}
    return retrieve_references_from_textbook_pages(
        lecture_pages=lecture_pages,
        textbook_chunks=reference_chunks,
        top_k=3,
    )


def _matching_explanation_for_current_lecture(config: Dict[str, Any]) -> Optional[Path]:
    if not config["generation"].get("use_explanations", True):
        return None

    lecture_pdf = config["input"].get("lecture_pdf")
    if not lecture_pdf:
        return None

    explanations_dir = config["input"].get("explanations_dir")
    if explanations_dir:
        return find_matching_explanation_in_dir(
            lecture_pdf=lecture_pdf,
            explanations_dir=explanations_dir,
            allowed_suffixes=config.get("matching", {}).get("allowed_explanation_suffixes", []),
        )

    fallback = config["input"].get("gpt_explanations")
    return Path(fallback) if fallback else None


def _setup_explanations(config: Dict[str, Any]) -> None:
    results = create_explanation_folders_for_lectures(
        lectures_dir=config["input"]["lectures_dir"],
        explanations_dir=config["input"]["explanations_dir"],
    )
    if not results:
        _fail(
            f"No lecture PDFs found in {config['input']['lectures_dir']}. "
            "Put .pdf files there before running --setup-explanations."
        )

    print(f"Lecture PDFs found: {len(results)}")
    for result in results:
        status = "created" if result.created else "exists"
        print(
            f"{status}: {result.explanation_file} "
            f"({result.page_count} slides from {result.lecture_pdf.name})"
        )
    print("Explanation folder setup complete. No PDFs were rendered and no API calls were made.")


def _split_explanations(config: Dict[str, Any], lecture_pdfs: List[Path]) -> None:
    results = split_explanations_for_lectures(
        lecture_pdfs=lecture_pdfs,
        explanations_dir=config["input"]["explanations_dir"],
        output_root_dir=config["output"]["root_dir"],
        allowed_suffixes=config.get("matching", {}).get("allowed_explanation_suffixes", []),
        overwrite_existing_notes=config["generation"]["overwrite_existing_notes"],
    )
    if not results:
        _fail(
            f"No lecture PDFs found in {config['input']['lectures_dir']}. "
            "Put .pdf files there before running --split-explanations."
        )

    print(f"Lectures to split: {len(results)}")
    for result in results:
        print("")
        print(f"Processing lecture: {result.lecture_pdf.name}")
        if result.explanation_file is None:
            print("Found explanation: none")
            print("Warning: no explanation markdown matched this lecture.")
        else:
            print(f"Found explanation: {_display_path(result.explanation_file)}")

        for note_path in result.created_notes:
            print(f"Created note: {_display_path(note_path)}")
        for note_path in result.skipped_notes:
            print(f"Skipped existing note: {_display_path(note_path)}")
        for page_number in result.missing_pages:
            print(f"Warning: no Slide/Page section found for page {page_number}.")

        print(
            "Summary: "
            f"{len(result.created_notes)} created, "
            f"{len(result.skipped_notes)} skipped, "
            f"{len(result.missing_pages)} missing."
        )

    print("")
    print("Explanation splitting complete. No PDFs were rendered and no API calls were made.")


def _load_gpt_explanations(
    explanation_file: Optional[Path],
    lecture_pages: Dict[int, str],
) -> Dict[int, str]:
    if not explanation_file:
        return {page_number: "" for page_number in lecture_pages}
    return load_gpt_explanations_by_page(explanation_file, page_numbers=lecture_pages.keys())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create annotated Korean explanation PDFs.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument("--lecture", default=None, help="Process only one specific lecture PDF.")
    parser.add_argument("--all", action="store_true", help="Process all PDFs in input/lectures.")
    parser.add_argument("--force-images", action="store_true", help="Re-render page images even if PNG files exist.")
    parser.add_argument(
        "--overwrite-notes",
        action="store_true",
        help="Regenerate markdown notes even if page_###.md files already exist.",
    )
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Skip note generation and render final PDFs from existing markdown notes.",
    )
    parser.add_argument(
        "--notes-only",
        action="store_true",
        help="Generate markdown notes but do not render final PDFs.",
    )
    parser.add_argument(
        "--test-sample",
        action="store_true",
        help="Create input/lectures/sample_lecture.pdf and process it.",
    )
    parser.add_argument(
        "--setup-explanations",
        action="store_true",
        help="Create input/explanations/{lecture_stem}/explanation.md templates and exit.",
    )
    parser.add_argument(
        "--split-explanations",
        action="store_true",
        help="Split matched explanation.md files into output/{lecture_stem}/notes/page_###.md and exit.",
    )
    return parser.parse_args()


def _display_path(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
