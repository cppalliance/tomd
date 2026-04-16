"""HTML to Markdown converter for WG21 papers."""

import logging
import os
from pathlib import Path

from .. import ascii_escape, format_front_matter
from . import extract as _extract
from . import render as _render

_log = logging.getLogger(__name__)


def convert_html(path: Path | os.PathLike[str]) -> tuple[str, str | None]:
    """Convert an HTML file to Markdown.

    Reads the file as UTF-8 (with replacement for decode errors).
    Returns (markdown_text, prompts_text_or_none).
    HTML conversion produces a prompts file only when sections
    cannot be converted cleanly.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")

    soup = _extract.parse_html(text)
    generator = _extract.detect_generator(soup)
    _log.debug("Generator: %s", generator)

    metadata = _extract.extract_metadata(soup, generator)
    problems = _extract.strip_boilerplate(soup, generator)

    body_md = _render.render_body(soup, generator)

    parts = []
    if metadata:
        parts.append(format_front_matter(metadata))

    if body_md.strip():
        parts.append(body_md.strip())

    md = "\n\n".join(parts)
    md = md.rstrip() + "\n"

    prompts = None
    if problems:
        prompt_parts = [
            "# tomd - HTML Conversion Issues",
            "",
            "The following issues were encountered during HTML-to-Markdown conversion.",
            "",
        ]
        for i, problem in enumerate(problems, 1):
            prompt_parts.append(f"## Issue {i}")
            prompt_parts.append("")
            prompt_parts.append(problem)
            prompt_parts.append("")
        prompts = "\n".join(prompt_parts)

    return ascii_escape(md), prompts
