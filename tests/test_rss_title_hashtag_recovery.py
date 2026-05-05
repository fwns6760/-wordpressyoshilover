import logging

import pytest

from src import rss_fetcher


FLAG = rss_fetcher.ENABLE_TITLE_HASHTAG_NAME_RECOVERY_ENV_FLAG
LOGGER = logging.getLogger("rss_fetcher")


@pytest.fixture
def custom_hashtag_roster(monkeypatch):
    monkeypatch.setattr(
        rss_fetcher,
        "_giants_roster_alias_index",
        lambda: (
            {"name": "赤星優志", "aliases": (rss_fetcher._normalize_roster_signal_text("赤星優志"),)},
            {"name": "ハワード", "aliases": (rss_fetcher._normalize_roster_signal_text("ハワード"),)},
            {
                "name": "山﨑伊織",
                "aliases": (
                    rss_fetcher._normalize_roster_signal_text("山﨑伊織"),
                    rss_fetcher._normalize_roster_signal_text("山崎伊織"),
                ),
            },
        ),
    )


def _run_subject_review_path(
    title: str,
    *,
    source_title: str,
    summary: str,
    article_subtype: str = "player",
):
    rewritten, review = rss_fetcher._finalize_title(
        title,
        source_title=source_title,
        summary=summary,
        analysis={},
    )
    if review is not None:
        return rewritten, review
    review = rss_fetcher._maybe_route_weak_subject_title_review(
        article_subtype=article_subtype,
        rewritten_title=rewritten,
        original_title=source_title,
        source_name="fixture",
        logger=LOGGER,
        source_title=source_title,
        source_body=summary,
        summary=summary,
    )
    return rewritten, review


def test_a1_recover_leading_punctuation_from_hashtag(custom_hashtag_roster, monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    rewritten, review = rss_fetcher._finalize_title(
        "、今季初先発で5回3安打無失点の快投も63球で降板",
        source_title="#赤星優志、今季初先発で5回3安打無失点の快投も63球で降板",
        summary="",
        analysis={},
    )

    assert rewritten == "赤星優志、今季初先発で5回3安打無失点の快投も63球で降板"
    assert review is None


def test_a1_flag_off_preserves_existing_title(custom_hashtag_roster, monkeypatch):
    monkeypatch.setenv(FLAG, "0")

    rewritten, review = rss_fetcher._finalize_title(
        "、今季初先発で5回3安打無失点の快投も63球で降板",
        source_title="#赤星優志、今季初先発で5回3安打無失点の快投も63球で降板",
        summary="",
        analysis={},
    )

    assert rewritten == "、今季初先発で5回3安打無失点の快投も63球で降板"
    assert review is None


def test_a2_recovers_missing_name_before_role(custom_hashtag_roster, monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    rewritten, review = rss_fetcher._finalize_title(
        "右アキレス腱炎からの復帰を目指す 投手がブルペン投球を実施",
        source_title="右アキレス腱炎からの復帰を目指す #ハワード 投手がブルペン投球を実施",
        summary="",
        analysis={},
    )

    assert rewritten == "右アキレス腱炎からの復帰を目指すハワード投手がブルペン投球を実施"
    assert review is None


def test_a3_non_roster_hashtag_skips_recovery_and_uses_existing_review_path(monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    rewritten, review = rss_fetcher._finalize_title(
        "投手「中野さんを切っていれば流れは変わった」 関連発言",
        source_title="#謎太郎 投手「中野さんを切っていれば流れは変わった」 関連発言",
        summary="",
        analysis={},
    )

    assert rewritten == "投手「中野さんを切っていれば流れは変わった」 関連発言"
    assert isinstance(review, rss_fetcher._WeakTitleReviewFallback)
    assert review.reason == "blacklist_phrase:関連発言"


def test_a4_clean_title_is_noop(custom_hashtag_roster, monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    rewritten, review = rss_fetcher._finalize_title(
        "赤星優志、今季初先発で5回3安打無失点の快投も63球で降板",
        source_title="#赤星優志、今季初先発で5回3安打無失点の快投も63球で降板",
        summary="",
        analysis={},
    )

    assert rewritten == "赤星優志、今季初先発で5回3安打無失点の快投も63球で降板"
    assert review is None


def test_a5_related_tail_keeps_existing_finalize_review(monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    rewritten, review = rss_fetcher._finalize_title(
        "選手「中野さんを切っていれば流れは変わった」 関連発言",
        source_title="#山崎伊織 選手「中野さんを切っていれば流れは変わった」 関連発言",
        summary="",
        analysis={},
    )

    assert rewritten == "山﨑伊織選手「中野さんを切っていれば流れは変わった」 関連発言"
    assert isinstance(review, rss_fetcher._WeakTitleReviewFallback)
    assert review.reason == "blacklist_phrase:関連発言"


def test_a6_leading_punctuation_without_hashtag_keeps_existing_title(monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    rewritten, review = rss_fetcher._finalize_title(
        "、今季初先発で5回3安打無失点の快投も63球で降板",
        source_title="今季初先発で5回3安打無失点の快投も63球で降板",
        summary="",
        analysis={},
    )

    assert rewritten == "、今季初先発で5回3安打無失点の快投も63球で降板"
    assert review is None
