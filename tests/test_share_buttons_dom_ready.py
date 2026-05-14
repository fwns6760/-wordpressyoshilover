"""2026-05-14 share button race condition regression guard.

Audit fix C: ``_SHARE_BUTTONS_SCRIPT_HTML`` must wait for
``DOMContentLoaded`` when the document is still loading so the second
share-aside block (emitted later in the body) gets its href rewritten
along with the first.
"""

from __future__ import annotations

import unittest

from src.tools import manual_intake as mi


class ShareButtonsDomReadyTests(unittest.TestCase):
    def test_script_reuses_named_function_for_listener_callback(self):
        # The IIFE must have a name (e.g. ``w``) so it can re-invoke
        # itself from a DOMContentLoaded listener.
        self.assertIn("(function w()", mi._SHARE_BUTTONS_SCRIPT_HTML)

    def test_script_defers_when_document_still_loading(self):
        # The race-condition guard must be present.
        self.assertIn(
            "document.readyState==='loading'",
            mi._SHARE_BUTTONS_SCRIPT_HTML,
        )
        self.assertIn(
            "addEventListener('DOMContentLoaded',w)",
            mi._SHARE_BUTTONS_SCRIPT_HTML,
        )

    def test_script_still_wires_x_line_copy_after_dom_ready(self):
        # The post-DOM-ready code path stays intact.
        self.assertIn(".nomotoke-share-x", mi._SHARE_BUTTONS_SCRIPT_HTML)
        self.assertIn(".nomotoke-share-line", mi._SHARE_BUTTONS_SCRIPT_HTML)
        self.assertIn(".nomotoke-share-copy", mi._SHARE_BUTTONS_SCRIPT_HTML)
        self.assertIn("twitter.com/intent/tweet", mi._SHARE_BUTTONS_SCRIPT_HTML)
        self.assertIn("social-plugins.line.me/lineit/share", mi._SHARE_BUTTONS_SCRIPT_HTML)
        self.assertIn("navigator.clipboard.writeText", mi._SHARE_BUTTONS_SCRIPT_HTML)

    def test_script_idempotency_guard_still_present(self):
        # Audit fix A invariant.
        self.assertIn("window.__nomotokeShareInit", mi._SHARE_BUTTONS_SCRIPT_HTML)
        self.assertIn("return", mi._SHARE_BUTTONS_SCRIPT_HTML)

    def test_build_share_buttons_block_includes_new_script(self):
        html = mi._build_share_buttons_block(with_script=True)
        self.assertIn("nomotoke-share-buttons", html)
        self.assertIn("document.readyState==='loading'", html)

    def test_build_share_buttons_block_without_script_excludes_listener(self):
        html = mi._build_share_buttons_block(with_script=False)
        self.assertIn("nomotoke-share-buttons", html)
        self.assertNotIn("DOMContentLoaded", html)


if __name__ == "__main__":
    unittest.main()
