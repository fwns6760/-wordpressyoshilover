from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tag_archives_are_noindexed_by_post_noindex_plugin():
    plugin = (ROOT / "src" / "yoshilover-post-noindex.php").read_text(encoding="utf-8")

    assert "is_tag()" in plugin
    assert "$robots['noindex'] = true;" in plugin
    assert "X-Robots-Tag: noindex, follow" in plugin
