import pytest

from src import tag_category_guard


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("  巨人   ニュース  ", "巨人 ニュース"),
        (" MLB  News ", "mlb news"),
        ("選手情報", "選手情報"),
        ("   ", ""),
    ],
)
def test_normalize_tag(tag, expected):
    assert tag_category_guard.normalize_tag(tag) == expected


def test_normalize_tags_preserves_order_and_deduplicates():
    tags = [" 巨人 ", "MLB", "", "巨人", "mlb", "スタメン 速報", "スタメン   速報"]
    assert tag_category_guard.normalize_tags(tags) == ["巨人", "mlb", "スタメン 速報"]


def test_validate_tags_warns_when_above_max_without_truncating():
    tags = [f"tag{i}" for i in range(tag_category_guard.TAG_MAX + 1)]
    kept, warnings = tag_category_guard.validate_tags(tags)

    assert kept == tags
    assert warnings == ["too many tags: 21 > 20"]


def test_validate_tags_warns_when_below_target():
    tags = [f"タグ{i}" for i in range(tag_category_guard.TAG_TARGET_LOW - 1)]
    kept, warnings = tag_category_guard.validate_tags(tags)

    assert kept == tags
    assert warnings == ["below target tags: 14 < 15"]


def test_validate_tags_warns_when_below_min():
    kept, warnings = tag_category_guard.validate_tags(["", "   "])

    assert kept == []
    assert warnings == ["too few tags: 0 < 1"]


@pytest.mark.parametrize("count", [tag_category_guard.TAG_TARGET_LOW, tag_category_guard.TAG_MAX])
def test_validate_tags_accepts_target_range_without_warnings(count):
    tags = [f"タグ{i}" for i in range(count)]
    kept, warnings = tag_category_guard.validate_tags(tags)

    assert kept == tags
    assert warnings == []


def test_validate_category_allows_known_category():
    normalized, warnings = tag_category_guard.validate_category("  試合結果  ")

    assert normalized == "試合結果"
    assert warnings == []


def test_validate_category_falls_back_to_other():
    normalized, warnings = tag_category_guard.validate_category("新カテゴリ")

    assert normalized == "その他"
    assert warnings == ["unknown category: 新カテゴリ -> その他"]


def test_validate_category_treats_blank_as_other():
    normalized, warnings = tag_category_guard.validate_category("   ")

    assert normalized == "その他"
    assert warnings == ["unknown category: (empty) -> その他"]
