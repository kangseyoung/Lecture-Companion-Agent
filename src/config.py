"""Load and validate the project YAML configuration.

The loader resolves paths relative to the config file location, validates input
files that are enabled in the generation settings, creates output directories,
and returns a normalized dictionary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

try:
    import yaml
except ImportError as exc:  # pragma: no cover - depends on local environment
    raise RuntimeError(
        "PyYAML is required to load config.yaml. Install it with: "
        "pip install -r requirements.txt"
    ) from exc


class ConfigError(ValueError):
    """Raised when config.yaml is missing required values or files."""


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load `config.yaml`, validate it, create output directories, and return a dict."""
    path = _find_config_file(config_path)
    raw_config = _read_yaml(path)
    base_dir = path.parent

    input_cfg = _required_section(raw_config, "input")
    output_cfg = _required_section(raw_config, "output")
    generation_cfg = _required_section(raw_config, "generation")
    layout_cfg = _required_section(raw_config, "layout")
    model_cfg = _required_section(raw_config, "model")
    matching_cfg = raw_config.get("matching", {})
    if matching_cfg and not isinstance(matching_cfg, Mapping):
        raise ConfigError("Invalid 'matching' section in config.yaml. Expected a mapping.")

    if "lectures_dir" in input_cfg:
        return _load_directory_config(
            base_dir=base_dir,
            input_cfg=input_cfg,
            output_cfg=output_cfg,
            generation_cfg=generation_cfg,
            matching_cfg=matching_cfg,
            layout_cfg=layout_cfg,
            model_cfg=model_cfg,
        )

    use_textbook = _required_bool(generation_cfg, "use_textbook", "generation")
    use_user_notes = _required_bool(generation_cfg, "use_user_notes", "generation")

    lecture_pdf = _resolve_path(base_dir, _required_string(input_cfg, "lecture_pdf", "input"))
    textbook_pdf = _optional_path(base_dir, input_cfg, "textbook_pdf", "input")
    user_notes = _optional_path(base_dir, input_cfg, "user_notes", "input")

    _require_existing_file(lecture_pdf, "input.lecture_pdf")

    if use_textbook:
        if textbook_pdf is None:
            raise ConfigError(
                "generation.use_textbook is true, but input.textbook_pdf is missing or empty."
            )
        _require_existing_file(textbook_pdf, "input.textbook_pdf")
    else:
        textbook_pdf = None

    if use_user_notes:
        if user_notes is None:
            raise ConfigError(
                "generation.use_user_notes is true, but input.user_notes is missing or empty."
            )
        _require_existing_file(user_notes, "input.user_notes")
    else:
        user_notes = None

    pages_dir = _resolve_path(base_dir, _required_string(output_cfg, "pages_dir", "output"))
    notes_dir = _resolve_path(base_dir, _required_string(output_cfg, "notes_dir", "output"))
    final_pdf = _resolve_path(base_dir, _required_string(output_cfg, "final_pdf", "output"))
    pages_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)
    final_pdf.parent.mkdir(parents=True, exist_ok=True)

    left_ratio = _required_number(layout_cfg, "left_width_ratio", "layout")
    right_ratio = _required_number(layout_cfg, "right_width_ratio", "layout")
    if left_ratio <= 0 or right_ratio <= 0:
        raise ConfigError("layout width ratios must be positive numbers.")
    if abs((left_ratio + right_ratio) - 1.0) > 0.001:
        raise ConfigError(
            "layout.left_width_ratio and layout.right_width_ratio must add up to 1.0 "
            f"(current total: {left_ratio + right_ratio:.3f})."
        )

    provider = _required_string(model_cfg, "provider", "model")
    if provider != "openai":
        raise ConfigError(f"Unsupported model.provider '{provider}'. Supported provider: openai.")

    return {
        "project_root": base_dir,
        "input": {
            "lecture_pdf": lecture_pdf,
            "textbook_pdf": textbook_pdf,
            "user_notes": user_notes,
            "gpt_explanations": _optional_path(base_dir, input_cfg, "gpt_explanations", "input"),
        },
        "output": {
            "pages_dir": pages_dir,
            "notes_dir": notes_dir,
            "final_pdf": final_pdf,
        },
        "generation": {
            "language": _required_string(generation_cfg, "language", "generation"),
            "note_style": _required_string(generation_cfg, "note_style", "generation"),
            "use_textbook": use_textbook,
            "use_user_notes": use_user_notes,
            "overwrite_existing_notes": _required_bool(
                generation_cfg, "overwrite_existing_notes", "generation"
            ),
        },
        "layout": {
            "page_size": _required_string(layout_cfg, "page_size", "layout"),
            "left_width_ratio": left_ratio,
            "right_width_ratio": right_ratio,
            "margin": _required_int(layout_cfg, "margin", "layout"),
        },
        "model": {
            "provider": provider,
            "model_name": _required_string(model_cfg, "model_name", "model"),
        },
    }


def _load_directory_config(
    base_dir: Path,
    input_cfg: Mapping[str, Any],
    output_cfg: Mapping[str, Any],
    generation_cfg: Mapping[str, Any],
    matching_cfg: Mapping[str, Any],
    layout_cfg: Mapping[str, Any],
    model_cfg: Mapping[str, Any],
) -> Dict[str, Any]:
    lectures_dir = _resolve_path(base_dir, _required_string(input_cfg, "lectures_dir", "input"))
    references_dir = _resolve_path(base_dir, _required_string(input_cfg, "references_dir", "input"))
    explanations_dir = _resolve_path(base_dir, _required_string(input_cfg, "explanations_dir", "input"))
    _ensure_directory(lectures_dir, "input.lectures_dir")
    _ensure_directory(references_dir, "input.references_dir")
    _ensure_directory(explanations_dir, "input.explanations_dir")

    output_root = _resolve_path(base_dir, _required_string(output_cfg, "root_dir", "output"))
    pages_dir = output_root / "pages"
    notes_dir = output_root / "notes"
    final_pdf = output_root / "final" / "annotated_explanation.pdf"
    pages_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)
    final_pdf.parent.mkdir(parents=True, exist_ok=True)

    use_references = _required_bool(generation_cfg, "use_references", "generation")
    use_explanations = _required_bool(generation_cfg, "use_explanations", "generation")
    lecture_pdfs = _sorted_files(lectures_dir, [".pdf"])
    reference_pdfs = _sorted_files(references_dir, [".pdf"]) if use_references else []
    explanation_files = _sorted_files(explanations_dir, [".md", ".markdown"]) if use_explanations else []

    left_ratio = _required_number(layout_cfg, "left_width_ratio", "layout")
    right_ratio = _required_number(layout_cfg, "right_width_ratio", "layout")
    if left_ratio <= 0 or right_ratio <= 0:
        raise ConfigError("layout width ratios must be positive numbers.")
    if abs((left_ratio + right_ratio) - 1.0) > 0.001:
        raise ConfigError(
            "layout.left_width_ratio and layout.right_width_ratio must add up to 1.0 "
            f"(current total: {left_ratio + right_ratio:.3f})."
        )

    provider = _required_string(model_cfg, "provider", "model")
    if provider != "openai":
        raise ConfigError(f"Unsupported model.provider '{provider}'. Supported provider: openai.")

    allowed_suffixes = _string_list(
        matching_cfg,
        "allowed_explanation_suffixes",
        default=[
            "_explanation",
            "_explanations",
            "_notes",
            "_gpt",
            "_설명",
            "_해설",
        ],
    )

    return {
        "project_root": base_dir,
        "input": {
            "lectures_dir": lectures_dir,
            "references_dir": references_dir,
            "explanations_dir": explanations_dir,
            "lecture_pdfs": lecture_pdfs,
            "reference_pdfs": reference_pdfs,
            "explanation_files": explanation_files,
            # Compatibility keys for the current single-lecture pipeline.
            "lecture_pdf": lecture_pdfs[0] if lecture_pdfs else None,
            "textbook_pdf": reference_pdfs[0] if reference_pdfs else None,
            "user_notes": None,
            "gpt_explanations": explanation_files[0] if explanation_files else None,
        },
        "output": {
            "root_dir": output_root,
            "pages_dir": pages_dir,
            "notes_dir": notes_dir,
            "final_pdf": final_pdf,
        },
        "generation": {
            "language": "Korean",
            "note_style": "beginner_explanation",
            "use_references": use_references,
            "use_explanations": use_explanations,
            # Compatibility keys for existing pipeline modules.
            "use_textbook": use_references,
            "use_user_notes": False,
            "overwrite_existing_notes": _required_bool(
                generation_cfg, "overwrite_existing_notes", "generation"
            ),
        },
        "matching": {
            "explanation_match_strategy": _required_string(
                matching_cfg, "explanation_match_strategy", "matching"
            )
            if matching_cfg
            else "stem_contains",
            "allowed_explanation_suffixes": allowed_suffixes,
        },
        "layout": {
            "page_size": _required_string(layout_cfg, "page_size", "layout"),
            "left_width_ratio": left_ratio,
            "right_width_ratio": right_ratio,
            "margin": _required_int(layout_cfg, "margin", "layout"),
        },
        "model": {
            "provider": provider,
            "model_name": _required_string(model_cfg, "model_name", "model"),
        },
    }


def _find_config_file(config_path: str) -> Path:
    path = Path(config_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists() and config_path == "config.yaml":
        path = Path(__file__).resolve().parents[1] / "config.yaml"
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    if path.suffix.lower() not in {".yaml", ".yml"}:
        raise ConfigError(f"Config file must be a YAML file: {path}")
    return path.resolve()


def _read_yaml(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read config file {path}: {exc}") from exc

    if not isinstance(data, Mapping):
        raise ConfigError(f"Config file must contain a top-level mapping: {path}")
    return data


def _required_section(config: Mapping[str, Any], section: str) -> Mapping[str, Any]:
    value = config.get(section)
    if not isinstance(value, Mapping):
        raise ConfigError(f"Missing or invalid '{section}' section in config.yaml.")
    return value


def _required_string(section: Mapping[str, Any], key: str, section_name: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Missing or invalid {section_name}.{key}: expected a non-empty string.")
    return value


def _required_bool(section: Mapping[str, Any], key: str, section_name: str) -> bool:
    value = section.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"Missing or invalid {section_name}.{key}: expected true or false.")
    return value


def _required_number(section: Mapping[str, Any], key: str, section_name: str) -> float:
    value = section.get(key)
    if not isinstance(value, (int, float)):
        raise ConfigError(f"Missing or invalid {section_name}.{key}: expected a number.")
    return float(value)


def _required_int(section: Mapping[str, Any], key: str, section_name: str) -> int:
    value = section.get(key)
    if not isinstance(value, int):
        raise ConfigError(f"Missing or invalid {section_name}.{key}: expected an integer.")
    return value


def _optional_path(
    base_dir: Path,
    section: Mapping[str, Any],
    key: str,
    section_name: str,
) -> Optional[Path]:
    value = section.get(key)
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ConfigError(f"Invalid {section_name}.{key}: expected a path string.")
    return _resolve_path(base_dir, value)


def _ensure_directory(path: Path, config_key: str) -> None:
    if path.exists() and not path.is_dir():
        raise ConfigError(f"Path for {config_key} exists but is not a directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _sorted_files(directory: Path, suffixes: List[str]) -> List[Path]:
    normalized_suffixes = {suffix.lower() for suffix in suffixes}
    return sorted(
        path.resolve()
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in normalized_suffixes
    )


def _string_list(section: Mapping[str, Any], key: str, default: List[str]) -> List[str]:
    if not section or key not in section:
        return list(default)
    value = section.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"Missing or invalid matching.{key}: expected a list of strings.")
    return value


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _require_existing_file(path: Path, config_key: str) -> None:
    if not path.exists():
        raise ConfigError(f"Required file does not exist for {config_key}: {path}")
    if not path.is_file():
        raise ConfigError(f"Path for {config_key} exists but is not a file: {path}")
