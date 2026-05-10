from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "src" / "yoshilover-063-frontend.php"


def _plugin_source() -> str:
    return PLUGIN.read_text(encoding="utf-8")


def _adsense_scroll_ui_section() -> str:
    src = _plugin_source()
    start = src.index("function yoshilover_063_enqueue_adsense_scroll_ui_assets()")
    end = src.index("\nfunction ", start + len("function yoshilover_063_enqueue_adsense_scroll_ui_assets()"))
    return src[start:end]


def test_adsense_scroll_ui_targets_existing_swell_adsense_widgets_only():
    src = _adsense_scroll_ui_section()

    assert "yoshilover_063_enqueue_adsense_scroll_ui_assets" in src
    assert ".widget_swell_ad_widget" in src
    assert "ins.adsbygoogle" in src
    assert 'script[src*="pagead2.googlesyndication.com"]' in src

    assert 'data-ad-client="ca-pub-' not in src
    assert 'data-ad-slot="3682593311"' not in src
    assert "<ins class=\"adsbygoogle\"" not in src


def test_adsense_scroll_ui_is_singular_post_only_and_non_silent():
    src = _plugin_source()

    assert "function yoshilover_063_should_render_adsense_scroll_ui()" in src
    assert "is_admin()" in src
    assert "is_feed()" in src
    assert "is_search()" in src
    assert "is_404()" in src
    assert "is_singular( 'post' )" in src

    assert "doc.dataset.yoshiAdsenseSlotCount" in src
    assert "String(adWidgets.length)" in src


def test_adsense_scroll_ui_uses_intersection_observer_without_close_overlay():
    src = _adsense_scroll_ui_section()

    assert "IntersectionObserver" in src
    assert "is-yoshi-adsense-inview" in src
    assert "is-yoshi-adsense-active" in src
    assert "prefers-reduced-motion: reduce" in src

    assert "yoshi-adsense-slot__close" not in src
    assert "dismiss" not in src.lower()


def test_adsense_scroll_ui_has_desktop_sidewinder_that_stops_at_article_end():
    src = _adsense_scroll_ui_section()

    assert "setupSidewinder" in src
    assert "matchMedia('(min-width: 1100px)')" in src
    assert "#main_content, .l-mainContent, main, #main" in src
    assert "is-yoshi-adsense-sidewinder-fixed" in src
    assert "is-yoshi-adsense-sidewinder-absolute" in src
    assert "getBoundingClientRect" in src
    assert "requestAnimationFrame" in src


def test_adsense_scroll_ui_keeps_mobile_ads_inline_without_fixed_overlay():
    src = _adsense_scroll_ui_section()
    mobile_start = src.index("@media (max-width: 768px)")
    mobile_end = src.index("@media (prefers-reduced-motion: reduce)", mobile_start)
    mobile_css = src[mobile_start:mobile_end]

    assert "yoshi-adsense-slot--mobile-inline" in src
    assert "doc.dataset.yoshiAdsenseMobileSlotCount" in src
    assert "box-shadow" in mobile_css
    assert "position: fixed" not in mobile_css
