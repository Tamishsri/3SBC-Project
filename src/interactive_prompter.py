"""Interactive Field Prompter & Learning Engine for ATS Form Filler.

When enabled via `--interactive`, prompts the user in the terminal for any
unmapped, required, or ambiguous ATS form questions encountered in real-time,
fills them immediately in the browser, and optionally persists the answers
into the candidate's `custom_answers` / presets so it learns for future applications.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from src.models import CandidateData

logger = logging.getLogger(__name__)
console = Console(safe_box=True)


def prompt_user_for_field(
    label: str,
    field_type: str = "text",
    choices: list[str] | None = None,
    default_value: str | None = None,
    input_func: Callable[[str], str] | None = None,
    confirm_func: Callable[[str], bool] | None = None,
) -> str | None:
    """Prompt the user via terminal for an unmapped question answer.

    Args:
        label: The visible label or prompt of the form question.
        field_type: Type of field ('text', 'textarea', 'dropdown', 'checkbox').
        choices: Optional list of dropdown choices.
        default_value: Default answer if user presses Enter.
        input_func: Optional mockable input function for unit tests.
        confirm_func: Optional mockable confirm function for unit tests.

    Returns:
        The string answer provided by the user, or None if skipped.
    """
    console.print()
    panel_content = (
        f"[bold yellow]Unmapped Field Encountered:[/] [white]{label}[/]\n"
        f"[dim]Field Type: {field_type}[/]"
    )
    if choices:
        formatted_choices = ", ".join(f"'{c}'" for c in choices[:6])
        if len(choices) > 6:
            formatted_choices += f" ... (+{len(choices)-6} more)"
        panel_content += f"\n[dim]Available Options: {formatted_choices}[/]"

    console.print(Panel(
        panel_content,
        title="[bold yellow]❓ Interactive Prompter (Human Input Needed)[/]",
        border_style="yellow",
    ))

    if input_func is not None:
        raw_val = input_func(f"Enter value for '{label}': ")
        return raw_val.strip() if raw_val else default_value

    try:
        if choices and len(choices) <= 10:
            prompt_text = f"[bold cyan]Select an option or enter custom text[/] [dim](default: {default_value or 'skip'})[/]"
            val = Prompt.ask(prompt_text, default=default_value or "")
        else:
            val = Prompt.ask(f"[bold cyan]Enter answer for '{label}'[/] [dim](press Enter to skip)[/]", default=default_value or "")

        return val.strip() if val.strip() else None
    except (KeyboardInterrupt, EOFError):
        console.print("[dim]Skipped interactive prompt.[/]")
        return None


def persist_learned_answer(
    candidate: CandidateData,
    label: str,
    answer: str,
    candidate_file: str | Path | None = None,
    save_to_disk: bool = True,
) -> bool:
    """Persist a learned question answer into candidate data and file.

    Args:
        candidate: CandidateData object to update in-memory.
        label: Question label key.
        answer: Provided answer.
        candidate_file: Path to candidate JSON to update on disk.
        save_to_disk: Whether to write back to the JSON file.

    Returns:
        True if persisted successfully.
    """
    clean_key = label.strip().lower()
    candidate.custom_answers[clean_key] = answer
    logger.info("[PROMPTER] Learned new answer for '%s' -> '%s'", clean_key, answer)

    if save_to_disk and candidate_file:
        try:
            p = Path(candidate_file)
            if p.is_file():
                raw = json.loads(p.read_text(encoding="utf-8"))
                if "custom_answers" not in raw:
                    raw["custom_answers"] = {}
                raw["custom_answers"][clean_key] = answer
                p.write_text(json.dumps(raw, indent=2), encoding="utf-8")
                logger.info("[PROMPTER] Updated candidate JSON on disk: %s", p)
                return True
        except Exception as exc:
            logger.warning("[PROMPTER] Could not write learned answer to file: %s", exc)

    return True
