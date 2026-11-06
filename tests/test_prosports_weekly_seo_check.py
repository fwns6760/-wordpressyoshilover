import datetime as dt

from src.prosports_weekly_seo_check import (
    Post,
    Report,
    cannibal_candidates,
    cohort_impr_per_post,
    compute_flags,
    page_key,
    render,
)

TODAY = dt.date(2026, 11, 5)
S = "https://prosports.yoshilover.com/"


def _post(i, age, slug="p"):
    return Post(i, TODAY - dt.timedelta(days=age), f"{S}{slug}{i}/", f"{slug}{i}")


def test_page_key_strips_fragment_and_decodes():
    assert page_key(f"{S}%E3%81%82/#index_id0") == f"{S}あ/"


def test_cohort_uses_only_posts_in_age_band():
    posts = [_post(1, 10), _post(2, 20), _post(3, 30), _post(4, 50)]
    impr = {f"{S}p2/": 100.0, f"{S}p3/": 300.0, f"{S}p4/": 9999.0}
    assert cohort_impr_per_post(posts, impr, TODAY, 14, 35) == (2, 200.0)
    assert cohort_impr_per_post(posts, impr, TODAY, 60, 90) == (0, 0.0)


def test_cannibal_ignores_home_and_hub_pages_and_small_pages():
    rows = [
        {"keys": [f"{S}a-yome/", "田中 嫁"], "impressions": 500},
        {"keys": [f"{S}a-kazoku/", "田中 実家"], "impressions": 200},
        {"keys": [f"{S}a-jitaku/", "田中 自宅"], "impressions": 800},
        {"keys": [f"{S}giants-geneki-tsuma-kazoku/", "田中"], "impressions": 900},
        {"keys": [f"{S}b/", "佐藤 嫁"], "impressions": 500},
        {"keys": [f"{S}b2/", "佐藤 子供"], "impressions": 20},
    ]
    out = cannibal_candidates(rows)
    assert set(out) == {"田中"}
    assert set(out["田中"]) == {f"{S}a-yome/", f"{S}a-kazoku/"}


def _report(**kw):
    rep = Report(today=TODAY, window_cur=("2026-10-07", "2026-11-03"), window_prev=("2026-09-09", "2026-10-06"))
    for k, v in kw.items():
        setattr(rep, k, v)
    return rep


def test_flags_clean_when_everything_is_healthy():
    rep = _report(
        new_posts=[_post(i, 1) for i in range(10)],
        new_states={f"{S}p{i}/": "Submitted and indexed" for i in range(10)},
        cohort_cur=(30, 1200.0), cohort_prev=(30, 1000.0),
        site_cur=(500000, 20000), site_prev=(450000, 18000),
    )
    assert compute_flags(rep) == []
    subject, body = render(rep)
    assert subject.startswith("【prosports】")
    assert "異常なし" in body


def test_flags_fire_on_index_rate_cohort_and_site_drop():
    states = {f"{S}p{i}/": ("Submitted and indexed" if i < 5 else "Crawled - currently not indexed") for i in range(10)}
    rep = _report(
        new_posts=[_post(i, 1) for i in range(10)],
        new_states=states,
        cohort_cur=(30, 400.0), cohort_prev=(30, 1000.0),
        site_cur=(200000, 9000), site_prev=(500000, 20000),
    )
    rep.flags = compute_flags(rep)
    assert len(rep.flags) == 4
    subject, body = render(rep)
    assert subject.startswith("【要確認】")
    assert "■ 要確認" in body


def test_flags_need_enough_posts_before_judging():
    rep = _report(
        new_posts=[_post(i, 1) for i in range(3)],
        new_states={f"{S}p{i}/": "Discovered - currently not indexed" for i in range(3)},
        cohort_cur=(5, 10.0), cohort_prev=(5, 1000.0),
        site_cur=(100, 1), site_prev=(5000, 50),
    )
    assert compute_flags(rep) == []


def test_stragglers_only_between_2_and_14_days_and_not_indexed():
    from src.prosports_weekly_seo_check import render_daily, stragglers
    posts = [_post(1, 1), _post(2, 3), _post(3, 10), _post(4, 20), _post(5, 5)]
    states = {
        f"{S}p1/": "URL is unknown to Google",            # too young
        f"{S}p2/": "Discovered - currently not indexed",
        f"{S}p3/": "Submitted and indexed",
        f"{S}p4/": "URL is unknown to Google",            # too old
        # p5 missing -> UNKNOWN
    }
    found = stragglers(posts, states, TODAY)
    assert [(p.id, age) for p, _, age in found] == [(5, 5), (2, 3)]
    subject, body = render_daily(TODAY, found, len(posts))
    assert subject.startswith("【要URL検査】") and "未登録 2 本" in subject
    assert "検出済み" in body and f"{S}p5/" in body


def test_ai_visibility_windows_splits_last_and_prior_seven_days():
    from src.prosports_weekly_seo_check import ai_visibility_windows
    days = {
        "2026-11-04": {"bot": {"GPTBot": 2, "ClaudeBot": 1}, "ref": {"chatgpt.com": 1}},
        "2026-10-30": {"bot": {"GPTBot": 5}, "ref": {}},          # day -6 -> current window
        "2026-10-29": {"bot": {"GPTBot": 7}, "ref": {"perplexity.ai": 3}},  # day -7 -> current window edge
        "2026-10-28": {"bot": {"GPTBot": 100}},                    # day -8 -> prior window
        "2026-10-22": {"bot": {"PerplexityBot": 4}},               # day -14 -> prior window edge
        "2026-10-21": {"bot": {"PerplexityBot": 999}},             # day -15 -> dropped
        "2026-11-05": {"bot": {"GPTBot": 999}},                    # today -> dropped (day incomplete)
        "garbage": {"bot": {"GPTBot": 1}},
    }
    bots, refs = ai_visibility_windows(days, TODAY)
    assert bots == {"GPTBot": (14, 100), "PerplexityBot": (0, 4), "ClaudeBot": (1, 0)}
    assert refs == {"perplexity.ai": (3, 0), "chatgpt.com": (1, 0)}
    assert ai_visibility_windows({}, TODAY) == ({}, {})


def test_render_shows_ai_section_or_unavailable():
    rep = Report(today=TODAY, window_cur=("a", "b"), window_prev=("c", "d"), ai_available=True,
                 ai_bots={"GPTBot": (14, 100)}, ai_refs={})
    _, body = render(rep)
    assert "AI 検索での見え方" in body and "GPTBot 14 (前 100)" in body and "訪問: なし" in body
    _, body = render(Report(today=TODAY, window_cur=("a", "b"), window_prev=("c", "d")))
    assert "取得できませんでした" in body
