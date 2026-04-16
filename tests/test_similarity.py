"""Tests for lib.similarity."""

from lib.similarity import _MAX_COMPARE_LENGTH, similar


def test_similar_identical():
    assert similar("hello world", "hello world")


def test_similar_minor_difference():
    assert similar("hello world", "hello worlds")


def test_similar_unrelated():
    assert not similar("hello world", "xyzzy foobar quux")


def test_similar_empty_strings():
    assert similar("", "")


def test_similar_one_empty():
    assert not similar("hello", "")


def test_similar_circuit_breaker():
    assert not similar("a" * (_MAX_COMPARE_LENGTH + 1), "b" * (_MAX_COMPARE_LENGTH + 1))


def test_similar_long_identical():
    assert similar("a" * (_MAX_COMPARE_LENGTH + 50), "a" * (_MAX_COMPARE_LENGTH + 50))


def test_similar_short_identical():
    assert similar("test", "test")


def test_similar_disjoint_words():
    assert not similar("aaa bbb", "ccc ddd")
