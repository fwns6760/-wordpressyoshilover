"""Unit tests for src.speech_quote_emphasizer."""
from __future__ import annotations

from src.speech_quote_emphasizer import wrap_speech_quotes

SPAN_OPEN = '<span style="color:#c54500;font-weight:700;font-size:1.3em">'
SPAN_CLOSE = "</span>"


def test_wraps_kagi_quote() -> None:
    out = wrap_speech_quotes("彼は「ありがとう」と返した。")
    assert out == f"彼は「{SPAN_OPEN}ありがとう{SPAN_CLOSE}」と返した。"


def test_wraps_double_bracket_quote() -> None:
    out = wrap_speech_quotes("作品『青い空』を読んだ。")
    assert out == f"作品『{SPAN_OPEN}青い空{SPAN_CLOSE}』を読んだ。"


def test_wraps_quote_with_inner_br() -> None:
    src = "<p>父は「よっしゃー！<br />！<br />」と叫んだ。</p>"
    out = wrap_speech_quotes(src)
    assert (
        f"「{SPAN_OPEN}よっしゃー！<br />！<br />{SPAN_CLOSE}」" in out
    )


def test_multiple_quotes_in_paragraph() -> None:
    src = "彼は「A」と言い、私は「B」と返した。"
    out = wrap_speech_quotes(src)
    assert (
        out
        == f"彼は「{SPAN_OPEN}A{SPAN_CLOSE}」と言い、"
        f"私は「{SPAN_OPEN}B{SPAN_CLOSE}」と返した。"
    )


def test_does_not_cross_paragraph_boundary() -> None:
    src = "<p>彼は「ありがとう</p><p>と返した」と話した。</p>"
    out = wrap_speech_quotes(src)
    # 「 has no matching 」 within the same <p>, so it stays untouched.
    assert SPAN_OPEN not in out
    assert out == src


def test_idempotent() -> None:
    once = wrap_speech_quotes("「ありがとう」")
    twice = wrap_speech_quotes(once)
    assert once == twice


def test_empty_string_passthrough() -> None:
    assert wrap_speech_quotes("") == ""


def test_no_quotes_unchanged() -> None:
    src = "<p>普通の地の文だけです。</p>"
    assert wrap_speech_quotes(src) == src


def test_does_not_touch_nested_html_attribute_quotes() -> None:
    # ASCII double-quotes inside attributes must not be affected.
    src = '<a href="https://example.com" class="x">link</a>'
    assert wrap_speech_quotes(src) == src
