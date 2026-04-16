"""String similarity algorithms for fuzzy matching.

Two independent algorithms with per-algorithm thresholds:
  1. SequenceMatcher - character-level (difflib, stdlib)
  2. Jaccard - word-level set overlap

A 200-character circuit breaker protects against expensive
comparisons on paragraph-length strings.
"""

from difflib import SequenceMatcher as _SM

_MAX_COMPARE_LENGTH = 200

_SEQUENCE_THRESHOLD = 0.75
_JACCARD_THRESHOLD = 0.65


def _sequence_similarity(a: str, b: str) -> float:
    """Character-level similarity using difflib.SequenceMatcher.

    Returns 0.0-1.0. Caller is responsible for the length guard.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return _SM(None, a, b).ratio()


def _jaccard_similarity(a: str, b: str) -> float:
    """Word-level similarity using set intersection/union.

    Returns 0.0-1.0. Caller is responsible for the length guard.
    Systematically scores lower than SequenceMatcher on short strings
    with one extra word.
    """
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    intersection = sa & sb
    union = sa | sb
    return len(intersection) / len(union)


def similar(a: str, b: str) -> bool:
    """True if EITHER algorithm scores above its calibrated threshold.

    The per-string check is lenient because the caller (TOC detection)
    provides a second guard via the 3+ consecutive run requirement.
    Identical strings short-circuit to True regardless of length; the
    200-char gate only protects against expensive fuzzy-compare work.
    """
    if a == b:
        return True
    if len(a) > _MAX_COMPARE_LENGTH or len(b) > _MAX_COMPARE_LENGTH:
        return False
    if _sequence_similarity(a, b) >= _SEQUENCE_THRESHOLD:
        return True
    if _jaccard_similarity(a, b) >= _JACCARD_THRESHOLD:
        return True
    return False
