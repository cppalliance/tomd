"""Golden regression: full PDF papers vs committed expected Markdown."""

import difflib
from pathlib import Path

import pytest

from lib.pdf import convert_pdf

_GOLDEN = Path(__file__).resolve().parent / "fixtures" / "golden"

_GOLDEN_STEMS = (
    "p0533r9",
    "p0957r8",
    "p1068r11",
    "p3556r0",
    "p1122r3",
    "p2040r0",
    "p3714r0",
    "p1112r4",
)


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _diff_head(actual: str, golden: str, limit: int = 120) -> str:
    a_lines = _normalize_newlines(actual).splitlines(keepends=True)
    b_lines = _normalize_newlines(golden).splitlines(keepends=True)
    diff = difflib.unified_diff(
        b_lines, a_lines, fromfile="golden", tofile="actual", n=3,
    )
    return "".join(list(diff)[:limit])


@pytest.mark.parametrize("stem", _GOLDEN_STEMS)
def test_convert_pdf_matches_golden(stem: str):
    pdf_path = _GOLDEN / f"{stem}.pdf"
    if not pdf_path.is_file():
        pytest.skip(f"missing PDF fixture: {pdf_path}")

    md, prompts = convert_pdf(pdf_path)
    golden_md = _GOLDEN / f"{stem}.golden.md"
    assert golden_md.is_file(), f"missing golden: {golden_md}"
    expected_md = golden_md.read_text(encoding="utf-8")
    got_md = _normalize_newlines(md)
    exp_md = _normalize_newlines(expected_md)
    if got_md != exp_md:
        pytest.fail(
            f"Markdown mismatch for {stem}\n{_diff_head(md, expected_md)}",
        )

    golden_prompts = _GOLDEN / f"{stem}.golden.prompts.md"
    if golden_prompts.is_file():
        assert prompts is not None, f"expected prompts for {stem}"
        exp_p = golden_prompts.read_text(encoding="utf-8")
        got_p = _normalize_newlines(prompts)
        exp_pn = _normalize_newlines(exp_p)
        if got_p != exp_pn:
            pytest.fail(
                f"Prompts mismatch for {stem}\n{_diff_head(prompts, exp_p)}",
            )
    else:
        assert prompts is None, f"unexpected prompts for {stem}"
