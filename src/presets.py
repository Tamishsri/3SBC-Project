"""User preference presets manager for ATS Form Filler.

Allows users to save and reuse standard work authorization preferences,
EEOC demographics, default custom questions, and cover letter templates
across different job applications without editing raw JSONs every time.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.models import CandidateData, Demographics, WorkAuthorization

logger = logging.getLogger(__name__)

_DEFAULT_PRESETS_DIR = Path("presets")


def _sanitize_preset_name(name: str) -> str:
    """Ensure safe filename for presets."""
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.strip().lower())
    if not clean:
        raise ValueError("Preset name cannot be empty or contain only invalid characters.")
    return clean


def save_preset(
    name: str,
    preset_data: dict[str, Any],
    presets_dir: Path | None = None,
) -> Path:
    """Save a user preference preset to disk.

    Args:
        name: Unique preset identifier (e.g., 'default_us', 'india_senior').
        preset_data: Dictionary containing work_authorization, demographics, etc.
        presets_dir: Optional custom directory. Defaults to presets/.

    Returns:
        Path to the saved preset JSON file.
    """
    target_dir = presets_dir or _DEFAULT_PRESETS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _sanitize_preset_name(name)
    preset_path = target_dir / f"{safe_name}.json"

    # Schema wrapper
    payload = {
        "preset_name": safe_name,
        "schema_version": "1.0",
        "work_authorization": preset_data.get("work_authorization", {}),
        "demographics": preset_data.get("demographics", {}),
        "custom_answers": preset_data.get("custom_answers", {}),
        "cover_letter_template": preset_data.get("cover_letter_template") or preset_data.get("cover_letter", ""),
    }

    preset_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("[PRESETS] Preset saved: %s", preset_path)
    return preset_path


def load_preset(
    name: str,
    presets_dir: Path | None = None,
) -> dict[str, Any]:
    """Load a saved preset by name.

    Args:
        name: Name of the preset or direct path to JSON.
        presets_dir: Optional presets directory.

    Returns:
        Dictionary with preset configuration.

    Raises:
        FileNotFoundError: If preset file cannot be located.
    """
    target_dir = presets_dir or _DEFAULT_PRESETS_DIR
    safe_name = _sanitize_preset_name(name)
    preset_path = target_dir / f"{safe_name}.json"

    # Fallback to direct path check
    if not preset_path.is_file():
        direct_path = Path(name)
        if direct_path.is_file():
            preset_path = direct_path
        else:
            raise FileNotFoundError(
                f"Preset '{name}' not found in {target_dir.resolve()} or as direct file."
            )

    return json.loads(preset_path.read_text(encoding="utf-8"))


def list_presets(presets_dir: Path | None = None) -> list[str]:
    """List all available preset names.

    Args:
        presets_dir: Optional presets directory.

    Returns:
        List of preset names without .json extension.
    """
    target_dir = presets_dir or _DEFAULT_PRESETS_DIR
    if not target_dir.is_dir():
        return []

    return sorted([p.stem for p in target_dir.glob("*.json")])


def merge_candidate_with_preset(
    candidate: CandidateData,
    preset: dict[str, Any] | str,
    presets_dir: Path | None = None,
) -> CandidateData:
    """Non-destructively merge candidate data with a preset.

    Explicit candidate fields ALWAYS take precedence over preset defaults.

    Args:
        candidate: Original CandidateData instance.
        preset: Preset dict or name string to load.
        presets_dir: Optional presets directory.

    Returns:
        New or updated CandidateData instance with merged defaults.
    """
    if isinstance(preset, str):
        preset_dict = load_preset(preset, presets_dir=presets_dir)
    else:
        preset_dict = preset

    cand_dict = candidate.model_dump()

    # 1. Merge Work Authorization
    preset_auth = preset_dict.get("work_authorization", {})
    if preset_auth:
        cand_auth = cand_dict.get("work_authorization") or {}
        merged_auth = {}
        for key, val in preset_auth.items():
            if val is not None:
                merged_auth[key] = val
        # Candidate explicitly provided values override preset
        for key, val in cand_auth.items():
            if val is not None:
                merged_auth[key] = val
        cand_dict["work_authorization"] = merged_auth

    # 2. Merge Demographics
    preset_demo = preset_dict.get("demographics", {})
    if preset_demo:
        cand_demo = cand_dict.get("demographics") or {}
        merged_demo = {}
        for key, val in preset_demo.items():
            if val is not None:
                merged_demo[key] = val
        for key, val in cand_demo.items():
            if val is not None:
                merged_demo[key] = val
        cand_dict["demographics"] = merged_demo

    # 3. Merge Custom Answers
    preset_custom = preset_dict.get("custom_answers", {})
    if preset_custom:
        cand_custom = cand_dict.get("custom_answers") or {}
        merged_custom = {**preset_custom, **cand_custom}
        cand_dict["custom_answers"] = merged_custom

    # 4. Merge Cover Letter (if empty)
    template = preset_dict.get("cover_letter_template") or preset_dict.get("cover_letter")
    if not cand_dict.get("cover_letter") and template:
        cand_dict["cover_letter"] = template

    return CandidateData.model_validate(cand_dict)
