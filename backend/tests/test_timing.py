"""Unit tests for services/timing.py — allocate() only.

No network calls, no filesystem access, no language branching.
"""

import pytest

from app.models.token import Token
from app.services.timing import PAUSE_MULTIPLIER, allocate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tok(text: str, index: int = 0) -> Token:
    return Token(text=text, index=index, start=0, end=len(text))


def _toks(*words: str) -> list[Token]:
    pos = 0
    result = []
    for i, w in enumerate(words):
        result.append(Token(text=w, index=i, start=pos, end=pos + len(w)))
        pos += len(w) + 1  # +1 for a notional space
    return result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_tokens_returns_empty():
    assert allocate([], 1000) == []


def test_zero_duration_returns_empty():
    assert allocate(_toks("hello"), 0) == []


def test_negative_duration_returns_empty():
    assert allocate(_toks("hello"), -1) == []


# ---------------------------------------------------------------------------
# Single token
# ---------------------------------------------------------------------------

def test_single_token_spans_full_duration():
    entries = allocate(_toks("hello"), 1000)
    assert len(entries) == 1
    assert entries[0].start_ms == 0
    assert entries[0].end_ms == 1000


def test_single_token_text_preserved():
    tok = _tok("你好")
    entries = allocate([tok], 500)
    assert entries[0].token.text == "你好"


# ---------------------------------------------------------------------------
# Two equal-length tokens split duration evenly
# ---------------------------------------------------------------------------

def test_two_equal_tokens_split_evenly():
    entries = allocate(_toks("ab", "cd"), 1000)
    assert len(entries) == 2
    assert entries[0].start_ms == 0
    assert entries[0].end_ms == 500
    assert entries[1].start_ms == 500
    assert entries[1].end_ms == 1000


# ---------------------------------------------------------------------------
# Proportional allocation by character count
# ---------------------------------------------------------------------------

def test_longer_token_gets_more_time():
    # "hello" (5 chars) vs "I" (1 char) → ratio 5:1
    entries = allocate(_toks("hello", "I"), 6000)
    assert entries[0].end_ms - entries[0].start_ms == 5000
    assert entries[1].end_ms - entries[1].start_ms == 1000


def test_three_tokens_proportional():
    # weights 1, 2, 3 → durations 100, 200, 300 ms
    tokens = [
        Token(text="a", index=0, start=0, end=1),
        Token(text="bb", index=1, start=2, end=4),
        Token(text="ccc", index=2, start=5, end=8),
    ]
    entries = allocate(tokens, 600)
    assert entries[0].end_ms - entries[0].start_ms == 100
    assert entries[1].end_ms - entries[1].start_ms == 200
    assert entries[2].end_ms - entries[2].start_ms == 300


# ---------------------------------------------------------------------------
# Punctuation dwell
# ---------------------------------------------------------------------------

def test_punctuation_gets_extra_dwell():
    # word "ab" (2 chars, weight 2) vs "." (1 char, weight PAUSE_MULTIPLIER)
    # total weight = 2 + PAUSE_MULTIPLIER
    entries = allocate(
        [
            Token(text="ab", index=0, start=0, end=2),
            Token(text=".", index=1, start=2, end=3),
        ],
        1000,
    )
    word_dur = entries[0].end_ms - entries[0].start_ms
    punct_dur = entries[1].end_ms - entries[1].start_ms
    assert punct_dur > word_dur


def test_pause_multiplier_applied_correctly():
    # word "a" (weight 1) + "." (weight PAUSE_MULTIPLIER)
    total = 1 + PAUSE_MULTIPLIER
    expected_word_ms = round(1 / total * 1000)
    expected_punct_ms = 1000 - expected_word_ms  # last entry snap

    entries = allocate(
        [
            Token(text="a", index=0, start=0, end=1),
            Token(text=".", index=1, start=1, end=2),
        ],
        1000,
    )
    assert entries[0].end_ms - entries[0].start_ms == expected_word_ms
    assert entries[1].end_ms - entries[1].start_ms == expected_punct_ms


@pytest.mark.parametrize("punct", ["。", "！", "？", "…", "、", "，", "；", "：",
                                    ",", ".", "!", "?", ";", ":", "—", "–"])
def test_all_pause_chars_recognised(punct: str):
    tok_word = Token(text="a", index=0, start=0, end=1)
    tok_punct = Token(text=punct, index=1, start=1, end=1 + len(punct))
    entries = allocate([tok_word, tok_punct], 1000)
    punct_dur = entries[1].end_ms - entries[1].start_ms
    word_dur = entries[0].end_ms - entries[0].start_ms
    # Punctuation must receive more ms than a single-char word
    assert punct_dur > word_dur


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------

def test_entries_are_contiguous():
    entries = allocate(_toks("one", "two", "three"), 900)
    for i in range(1, len(entries)):
        assert entries[i].start_ms == entries[i - 1].end_ms


def test_no_negative_durations():
    entries = allocate(_toks("a", "b", "c", "d"), 100)
    for e in entries:
        assert e.end_ms >= e.start_ms


def test_last_entry_ends_at_total_ms():
    entries = allocate(_toks("hello", "world", "foo"), 777)
    assert entries[-1].end_ms == 777


def test_first_entry_starts_at_zero():
    entries = allocate(_toks("hello"), 500)
    assert entries[0].start_ms == 0


def test_token_count_preserved():
    tokens = _toks("a", "b", "c", "d", "e")
    entries = allocate(tokens, 1000)
    assert len(entries) == len(tokens)


def test_token_objects_preserved():
    tokens = _toks("apple", "banana")
    entries = allocate(tokens, 1000)
    assert entries[0].token.text == "apple"
    assert entries[1].token.text == "banana"


# ---------------------------------------------------------------------------
# Language-agnostic: same result for Chinese and English tokens
# ---------------------------------------------------------------------------

def test_language_agnostic_same_weights():
    zh_tokens = [
        Token(text="你好", index=0, start=0, end=2),
        Token(text="世界", index=1, start=2, end=4),
    ]
    en_tokens = [
        Token(text="ab", index=0, start=0, end=2),
        Token(text="cd", index=1, start=2, end=4),
    ]
    zh_entries = allocate(zh_tokens, 1000)
    en_entries = allocate(en_tokens, 1000)
    # Both are 2-char tokens; durations should be identical
    for zh_e, en_e in zip(zh_entries, en_entries):
        assert (zh_e.end_ms - zh_e.start_ms) == (en_e.end_ms - en_e.start_ms)


# ---------------------------------------------------------------------------
# Rounding: total always equals total_ms
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("total_ms", [1, 7, 100, 333, 1000, 9999])
def test_sum_of_durations_equals_total_ms(total_ms: int):
    entries = allocate(_toks("hello", "world", "foo"), total_ms)
    total = sum(e.end_ms - e.start_ms for e in entries)
    assert total == total_ms
