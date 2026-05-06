"""Regression tests for `_stale_source_guard_threshold_hours` defensive behavior.

Bug observed in live (2026-05-06 ~10:43 JST) when ENABLE_FETCHER_STALE_SOURCE_GUARD=1
was flipped: src/guarded_publish_evaluator.py:1711 had a Python 3.11 SyntaxError
(f-string + backslash) which crashed the lazy import inside
`_stale_source_guard_threshold_hours`, taking down the entire fetcher with
HTTP 500 + Traceback. Tests run on Python 3.13 (local) did not catch it because
3.13 allows the f-string syntax.

Fix in commit:
- guarded_publish_evaluator.py:1711 refactored: tail = re.sub(...) extracted
  before f-string (works on Python 3.11 / 3.12 / 3.13).
- rss_fetcher._stale_source_guard_threshold_hours wrapped with try/except so
  import or runtime failures fall back to 24h conservative default rather than
  crashing the fetcher.

These tests pin both invariants.
"""

import unittest
from unittest.mock import patch

from src import rss_fetcher


class StaleSourceGuardThresholdDefensiveTests(unittest.TestCase):
    """Threshold helper must never raise, regardless of subtype value."""

    def test_known_subtype_returns_evaluator_value(self):
        # manager / postgame / lineup are known categories; helper should
        # delegate to publish_evaluator._freshness_threshold_hours.
        result = rss_fetcher._stale_source_guard_threshold_hours("manager")
        self.assertIsInstance(result, float)
        self.assertGreater(result, 0.0)

    def test_none_subtype_does_not_raise(self):
        # None must be coerced internally and NOT raise.
        result = rss_fetcher._stale_source_guard_threshold_hours(None)
        self.assertIsInstance(result, float)
        self.assertGreater(result, 0.0)

    def test_empty_subtype_does_not_raise(self):
        result = rss_fetcher._stale_source_guard_threshold_hours("")
        self.assertIsInstance(result, float)
        self.assertGreater(result, 0.0)

    def test_unknown_subtype_returns_default(self):
        # Unknown subtype falls back to evaluator default (currently 24h).
        result = rss_fetcher._stale_source_guard_threshold_hours("totally_unknown_subtype_xyz")
        self.assertIsInstance(result, float)
        self.assertGreater(result, 0.0)

    def test_non_string_subtype_does_not_raise(self):
        # int / list / dict / object should be coerced with str() and not crash.
        for bad in (123, ["lineup"], {"subtype": "manager"}, object()):
            with self.subTest(value=bad):
                result = rss_fetcher._stale_source_guard_threshold_hours(bad)
                self.assertIsInstance(result, float)
                self.assertGreater(result, 0.0)

    def test_evaluator_import_failure_falls_back_to_default(self):
        # Simulate the live 2026-05-06 incident: evaluator module import
        # itself raises (e.g. SyntaxError, ImportError). Helper must NOT
        # propagate the exception.
        # Trick: setting sys.modules[X] = None causes `from X import Y` to
        # raise ImportError on next import lookup. We also clear the
        # attribute on `src` package so the cached attribute lookup does not
        # short-circuit the sys.modules check.
        import sys as _sys
        import src as _src

        cached_module = _sys.modules.pop("src.guarded_publish_evaluator", None)
        cached_attr = getattr(_src, "guarded_publish_evaluator", None)
        if hasattr(_src, "guarded_publish_evaluator"):
            delattr(_src, "guarded_publish_evaluator")
        _sys.modules["src.guarded_publish_evaluator"] = None  # type: ignore[assignment]
        try:
            result = rss_fetcher._stale_source_guard_threshold_hours("manager")
        finally:
            del _sys.modules["src.guarded_publish_evaluator"]
            if cached_module is not None:
                _sys.modules["src.guarded_publish_evaluator"] = cached_module
            if cached_attr is not None:
                setattr(_src, "guarded_publish_evaluator", cached_attr)

        self.assertIsInstance(result, float)
        self.assertEqual(result, rss_fetcher._STALE_SOURCE_GUARD_FALLBACK_THRESHOLD_HOURS)

    def test_evaluator_runtime_exception_falls_back_to_default(self):
        # Simulate evaluator._freshness_threshold_hours raising at runtime.
        from src import guarded_publish_evaluator as publish_evaluator

        with patch.object(publish_evaluator, "_freshness_threshold_hours", side_effect=RuntimeError("boom")):
            result = rss_fetcher._stale_source_guard_threshold_hours("manager")

        self.assertEqual(result, rss_fetcher._STALE_SOURCE_GUARD_FALLBACK_THRESHOLD_HOURS)


class GuardedPublishEvaluatorPython311CompatTests(unittest.TestCase):
    """Lock the Python 3.11 syntax compatibility of guarded_publish_evaluator.py.

    The live incident was a Python 3.11 SyntaxError (f-string + backslash)
    that production runtime (python:3.11-slim) hit but local Python 3.13 did
    not catch. We pin module compileability and `_placeholder_filler_outro_detail`
    behavior so any future regression is caught locally.
    """

    def test_module_imports_under_python_3_11_grammar(self):
        # ast.parse uses the running Python's grammar. Cannot directly emulate
        # 3.11 from a newer interpreter, but at minimum we verify the file is
        # syntactically valid for all currently-supported versions.
        import ast

        source = open("src/guarded_publish_evaluator.py", "r", encoding="utf-8").read()
        ast.parse(source)
        self.assertNotIn(
            "f\"filler_outro=1;tail={re.sub(r'\\\\s+', ' ', last_line).strip()}\"",
            source,
            "Restored Python 3.11-incompatible f-string with backslash inside expression part",
        )

    def test_placeholder_filler_outro_detail_runs(self):
        from src import guarded_publish_evaluator as publish_evaluator

        body = "本文プロローグ\n" + ("これは長めの本文文章です。" * 10) + "\n   filler-only line   "
        # Stub PLACEHOLDER_FILLER_OUTRO_RE to match our crafted last line so
        # we exercise the sub() path even if the real regex doesn't match.
        import re as _re

        with patch.object(
            publish_evaluator,
            "PLACEHOLDER_FILLER_OUTRO_RE",
            _re.compile(r"\s*filler-only line\s*"),
        ):
            result = publish_evaluator._placeholder_filler_outro_detail(body)

        self.assertIsNotNone(result)
        assert result is not None  # for mypy
        self.assertTrue(result.startswith("filler_outro=1;tail="))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
