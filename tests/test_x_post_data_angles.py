"""データ角度 v2 (勝利相関 / 対戦別split / 歴代通算チェイス / 話題ブースト) tests。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src import x_post_data_angles as angles


def _make_db(tmp_path: Path) -> str:
    """最小 fixture db: games + batting_logs (巨人 + 相手選手混在)。"""
    db = tmp_path / "insight.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE games (
            game_id TEXT PRIMARY KEY, game_date TEXT, opponent TEXT,
            result TEXT, giants_score INT, opp_score INT
        );
        CREATE TABLE batting_logs (
            game_id TEXT, team_role TEXT, team_name TEXT,
            player_canonical TEXT, AB INT, H INT, RBI INT
        );
        """
    )
    # 12 試合: 巨人選手「強打者」 RBI あり 8 試合 → 7勝1敗 / なし 4 試合 → 1勝3敗
    rows = []
    for i in range(12):
        gid = f"2026-05-{i + 1:02d}:g-t-{i + 1:02d}"
        has_rbi = i < 8
        win = (i < 7) or (i == 8)  # RBIあり8試合中7勝, なし4試合中1勝
        rows.append((gid, f"2026-05-{i + 1:02d}", "阪神" if i % 2 == 0 else "広島",
                     "win" if win else "loss"))
        conn.execute(
            "INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?)",
            (gid, "giants", "巨人", "強打者", 4, 2 if has_rbi else 0,
             1 if has_rbi else 0),
        )
        # 相手チーム選手 (team_role は陣営ラベルなので 'giants' でも team_name で除外
        # されること = 2026-06-11 周東混入 bug の回帰)
        conn.execute(
            "INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?)",
            (gid, "giants", "ソフトバンク", "周東佑京", 4, 3, 2),
        )
    conn.executemany("INSERT INTO games VALUES (?,?,?,?,0,0)", rows)
    conn.commit()
    conn.close()
    return str(db)


def test_win_correlation_numbers_exact(tmp_path):
    db = _make_db(tmp_path)
    out = angles.build_win_correlation_candidates(
        db, max_count=2, min_cond_games=5, min_total_games=10,
        min_gap=0.10, with_image=False,
    )
    assert len(out) == 1
    c = out[0]
    assert c.focus_player == "強打者"
    assert "7勝1敗" in c.post_text and "1勝3敗" in c.post_text
    assert ".875" in c.post_text and ".250" in c.post_text
    assert c.signature.startswith("win_corr|強打者|")


def test_win_correlation_excludes_non_giants(tmp_path):
    """team_role でなく team_name='巨人' で識別する (周東混入 bug 回帰)。"""
    db = _make_db(tmp_path)
    out = angles.build_win_correlation_candidates(
        db, max_count=10, min_cond_games=1, min_total_games=1,
        min_gap=-1.0, with_image=False,
    )
    assert all(c.focus_player != "周東佑京" for c in out)


def test_win_correlation_respects_dedup(tmp_path):
    db = _make_db(tmp_path)
    sig = "win_corr|強打者|rbi"
    out = angles.build_win_correlation_candidates(
        db, max_count=2, min_cond_games=5, min_total_games=10,
        min_gap=0.10, dedup_set={sig, "win_corr|強打者|multi_hit"},
        with_image=False,
    )
    assert out == []


def test_opponent_split_killer_angle(tmp_path):
    db = _make_db(tmp_path)
    # 強打者: 対阪神 6 試合 (RBIあり期 8 試合のうち偶数 idx) — fixture では
    # 対阪神 6 試合中 RBI あり 4 (H=2) + なし 2 (H=0) = 8安打/24打数 .333
    # シーズン 16安打/48打数 .333 → gap 0。 split を出すため広島側を弱くする
    # 代わりに、 閾値を緩めて検証する (gap 計算と除外規則のみ確認)。
    out = angles.build_opponent_split_candidates(
        db, max_count=5, min_opp_ab=5, min_season_ab=10,
        min_gap=-1.0, with_image=False,
    )
    assert all(c.focus_player != "周東佑京" for c in out)
    assert all(c.signature.startswith("opp_split|") for c in out)


def test_opponent_split_gap_threshold(tmp_path):
    db = _make_db(tmp_path)
    out = angles.build_opponent_split_candidates(
        db, max_count=5, min_opp_ab=5, min_season_ab=10,
        min_gap=0.500, with_image=False,
    )
    assert out == []  # gap .5 を超える split は fixture に無い


def test_alltime_chase_synthetic():
    rankings = {"hr": [
        {"rank": 10, "name": "OB大砲", "value": 250, "is_current": False, "slug": None},
        {"rank": 11, "name": "現役主砲", "value": 248, "is_current": True, "slug": "x"},
        {"rank": 12, "name": "OB次点", "value": 200, "is_current": False, "slug": None},
    ]}
    out = angles.build_alltime_chase_candidates(
        max_count=2, rankings=rankings, with_image=False)
    assert len(out) == 1
    c = out[0]
    assert "あと2本" in c.post_text and "OB大砲" in c.post_text
    assert c.signature == "alltime_chase|現役主砲|hr|248"


def test_alltime_chase_skips_far_targets():
    rankings = {"hr": [
        {"rank": 1, "name": "OB", "value": 500, "is_current": False, "slug": None},
        {"rank": 2, "name": "現役", "value": 100, "is_current": True, "slug": "x"},
    ]}
    out = angles.build_alltime_chase_candidates(
        max_count=2, rankings=rankings, max_remaining=8, with_image=False)
    assert out == []


class _Stub:
    def __init__(self, fp):
        self.focus_player = fp
        self.why_now = ""


def test_boost_topical_orders_by_mentions():
    cands = [_Stub("岡本和真"), _Stub("戸郷翔征"), _Stub("泉口友汰")]
    out = angles.boost_topical_candidates(cands, {"泉口友汰": 5, "岡本和真": 2})
    assert [c.focus_player for c in out] == ["泉口友汰", "岡本和真", "戸郷翔征"]
    assert "5件言及" in out[0].why_now
    assert out[2].why_now == ""


def test_boost_topical_min_mentions_gate():
    cands = [_Stub("A"), _Stub("B")]
    out = angles.boost_topical_candidates(cands, {"B": 1}, min_mentions=2)
    assert [c.focus_player for c in out] == ["A", "B"]  # 1 件は boost しない
    assert out[1].why_now == ""


def test_boost_topical_empty_inputs_passthrough():
    cands = [_Stub("A")]
    assert angles.boost_topical_candidates(cands, {}) is cands
    assert angles.boost_topical_candidates([], {"A": 3}) == []


def _rss_xml(items: list[tuple[str, str]]) -> str:
    """(text, pubdate) のリストから RSSHub 風 RSS 2.0 を組む。"""
    body = "".join(
        f"<item><title>{text}</title><description>{text}</description>"
        f"<link>https://x.com/t/{i}</link><pubDate>{pub}</pubDate></item>"
        for i, (text, pub) in enumerate(items)
    )
    return f"<rss><channel>{body}</channel></rss>"


def test_fetch_topical_counts_gates_by_age(monkeypatch):
    """6h 窓: 直近の言及だけ数え、 昨日の投稿は拾わない。"""
    from datetime import datetime, timezone, timedelta

    now = datetime(2026, 6, 11, 22, 0, tzinfo=timezone(timedelta(hours=9)))

    def fmt(dt):
        return dt.strftime("%a, %d %b %Y %H:%M:%S %z")

    xml = _rss_xml([
        ("岡本和真が逆転2ラン", fmt(now - timedelta(hours=1))),
        ("岡本和真 ヒーローインタビュー", fmt(now - timedelta(hours=2))),
        ("岡本和真 昨日の一発", fmt(now - timedelta(hours=30))),  # 窓外
    ])
    import src.x_post_mail_lane as lane
    monkeypatch.setattr(lane, "_load_giants_player_aliases",
                        lambda: {"岡本和真": "岡本和真"})
    monkeypatch.setattr(lane, "_load_giants_member_aliases", lambda: {})
    monkeypatch.setattr(
        lane, "detect_giants_player_name",
        lambda text, alias_map=None: "岡本和真" if "岡本和真" in text else "",
    )
    counts = angles.fetch_topical_counts(
        fetch_fn=lambda url: xml, handles=["hochi_giants"],
        max_age_hours=6.0, now=now,
    )
    assert counts == {"岡本和真": 2}  # 30h 前の 1 件は除外


def test_fetch_topical_counts_graceful_on_fetch_error():
    counts = angles.fetch_topical_counts(
        fetch_fn=lambda url: (_ for _ in ()).throw(RuntimeError("down")),
        handles=["hochi_giants"],
    )
    assert counts == {}


def test_hit_streak_counts_consecutive_games(tmp_path):
    """fixture: 強打者は RBI あり期 (直近側に並べ替え) — streak は H>0 連続数。"""
    db = tmp_path / "streak.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE games (game_id TEXT PRIMARY KEY, game_date TEXT, opponent TEXT,
            result TEXT, giants_score INT, opp_score INT);
        CREATE TABLE batting_logs (game_id TEXT, team_role TEXT, team_name TEXT,
            player_canonical TEXT, AB INT, H INT, RBI INT);
        """
    )
    # 新しい順に H: 1,2,1, 0, 3 → 現在 streak = 3
    hs = [1, 2, 1, 0, 3]
    for i, h in enumerate(hs):
        gid = f"2026-06-{10 - i:02d}:g-t-{i:02d}"
        conn.execute("INSERT INTO games VALUES (?,?,?,?,0,0)",
                     (gid, f"2026-06-{10 - i:02d}", "阪神", "win"))
        conn.execute("INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?)",
                     (gid, "giants", "巨人", "強打者", 4, h, 0))
    conn.commit()
    conn.close()
    assert angles._current_hit_streak(str(db), "強打者") == 3
    assert angles._streak_line(str(db), "強打者") == "📝3試合連続安打中\n"
    assert angles._streak_line(str(db), "強打者", min_streak=4) == ""
    assert angles._current_hit_streak(str(db), "居ない選手") == 0


def test_win_correlation_post_includes_streak_line(tmp_path):
    """fixture (連続安打 8 試合…直近 4 試合は H=0) — streak 0 なので行は出ない。"""
    db = _make_db(tmp_path)
    out = angles.build_win_correlation_candidates(
        db, max_count=1, min_cond_games=5, min_total_games=10,
        min_gap=0.10, with_image=False,
    )
    assert len(out) == 1
    # fixture は直近 (06-12 寄り) が H=0 のため streak 行なし
    assert "連続安打" not in out[0].post_text


def test_preferred_player_wins_over_larger_gap(tmp_path):
    """preferred_players (今夜の話題) は閾値を満たす限り gap より優先。"""
    db = tmp_path / "pref.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE games (game_id TEXT PRIMARY KEY, game_date TEXT, opponent TEXT,
            result TEXT, giants_score INT, opp_score INT);
        CREATE TABLE batting_logs (game_id TEXT, team_role TEXT, team_name TEXT,
            player_canonical TEXT, AB INT, H INT, RBI INT);
        """
    )
    # 大差選手 (gap 大) と 話題選手 (gap 小さめだが閾値内) の 2 人
    for i in range(12):
        gid = f"2026-05-{i + 1:02d}:g-t-{i:02d}"
        conn.execute("INSERT INTO games VALUES (?,?,?,?,0,0)",
                     (gid, f"2026-05-{i + 1:02d}", "阪神",
                      "win" if i < 6 else "loss"))
        # 大差選手: RBI と勝敗が完全一致 (gap 1.0)
        conn.execute("INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?)",
                     (gid, "giants", "巨人", "大差選手", 4, 1, 1 if i < 6 else 0))
        # 話題選手: RBI あり 6 試合中 4 勝 (gap 小)、 なし 6 試合中 2 勝
        conn.execute("INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?)",
                     (gid, "giants", "巨人", "話題選手", 4, 1,
                      1 if i in (0, 1, 2, 3, 6, 7) else 0))
    conn.commit()
    conn.close()
    base = angles.build_win_correlation_candidates(
        str(db), max_count=1, min_cond_games=3, min_total_games=10,
        min_gap=0.05, with_image=False)
    assert base[0].focus_player == "大差選手"  # 既定は gap 順
    pref = angles.build_win_correlation_candidates(
        str(db), max_count=1, min_cond_games=3, min_total_games=10,
        min_gap=0.05, with_image=False, preferred_players={"話題選手"})
    assert pref[0].focus_player == "話題選手"  # 話題選手が先頭


# ─── 週間MVP (月曜定番企画) ──────────────────────────────────────────


def _make_weekly_db(tmp_path: Path) -> str:
    """週間MVP 用 fixture: R / atbats_json 列込み。 先週 = 2026-06-08(月)〜06-14(日)。"""
    db = tmp_path / "weekly.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE games (
            game_id TEXT PRIMARY KEY, game_date TEXT, opponent TEXT,
            result TEXT, giants_score INT, opp_score INT
        );
        CREATE TABLE batting_logs (
            game_id TEXT, team_role TEXT, team_name TEXT,
            player_canonical TEXT, AB INT, H INT, RBI INT, R INT,
            atbats_json TEXT
        );
        """
    )
    # 週内 4 試合 + 週外 (前週) 1 試合
    for i, d in enumerate(("2026-06-09", "2026-06-10", "2026-06-12", "2026-06-13")):
        gid = f"{d}:g-t"
        conn.execute("INSERT INTO games VALUES (?,?,?,?,0,0)", (gid, d, "阪神", "win"))
        # MVP候補: 4試合 16打数8安打 (.500)、 HR2 (atbats_json「本」cell)、 6打点
        conn.execute(
            "INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?,?,?)",
            (gid, "giants", "巨人", "週間王", 4, 2, 1 if i < 2 else 2,
             1, '["右越本①", "中前安", "三 振", "遊ゴロ"]' if i < 2
             else '["中前安", "左前安", "三 振", "遊ゴロ"]'),
        )
        # 稼働不足 (AB 8 < min_ab 10) は対象外
        conn.execute(
            "INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?,?,?)",
            (gid, "giants", "巨人", "控え", 2, 1, 0, 0, '["中前安", "遊ゴロ"]'),
        )
    out_gid = "2026-06-07:g-t"
    conn.execute("INSERT INTO games VALUES (?,?,?,?,0,0)",
                 (out_gid, "2026-06-07", "広島", "win"))
    conn.execute(
        "INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?,?,?)",
        (out_gid, "giants", "巨人", "週間王", 4, 4, 4, 2,
         '["右越本①", "右越本①", "右越本①", "右越本①"]'),
    )
    conn.commit()
    conn.close()
    return str(db)


def test_weekly_mvp_numbers_exact(tmp_path):
    """週内集計のみ (前週日曜 6/7 の 4HR は入らない)、 HR は atbats_json 由来。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    db = _make_weekly_db(tmp_path)
    monday = datetime(2026, 6, 15, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    out = angles.build_weekly_mvp_candidates(db, now=monday, with_image=False)
    assert len(out) == 1
    c = out[0]
    assert c.focus_player == "週間王"
    assert "【週間MVP】週間王" in c.post_text
    assert ".500" in c.post_text and "8安打/16打数" in c.post_text
    assert "2本塁打" in c.post_text and "6打点" in c.post_text
    assert "6/8〜6/14" in c.post_text and "4試合" in c.post_text
    assert c.signature == "weekly_mvp|2026-06-08|週間王"


def test_weekly_mvp_monday_only(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    db = _make_weekly_db(tmp_path)
    tuesday = datetime(2026, 6, 16, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert angles.build_weekly_mvp_candidates(db, now=tuesday, with_image=False) == []
    monday = datetime(2026, 6, 15, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert angles.build_weekly_mvp_candidates(
        db, now=tuesday, with_image=False, monday_only=False) != []
    assert angles.build_weekly_mvp_candidates(db, now=monday, with_image=False)


def test_weekly_mvp_respects_dedup(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    db = _make_weekly_db(tmp_path)
    monday = datetime(2026, 6, 15, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    dedup = {"weekly_mvp|2026-06-08|週間王"}
    assert angles.build_weekly_mvp_candidates(
        db, now=monday, with_image=False, dedup_set=dedup) == []


# ─── 新旧比較 (同年齢レジェンド対比) ─────────────────────────────────


_LEGENDS_FIXTURE = {
    "往年の大砲": {
        "npb_id": "1", "birthdate": "1979年3月20日",
        "seasons": [
            {"年度": "2001", "本塁打": "13"},
            {"年度": "2002", "本塁打": "18"},
        ],
    },
    "現役の壁": {
        "npb_id": "2", "birthdate": "1996年6月30日",
        "seasons": [
            {"年度": "2016", "本塁打": "1"},
            {"年度": "2018", "本塁打": "33"},
        ],
    },
}


def _young_cache(birth: str, years: list) -> dict:
    return {
        "ids": {"若手　太郎": "999"},
        "players": {"999": {
            "profile": {"birthdate": birth},
            "batting": {"years": years},
        }},
    }


def test_legend_compare_beats_one_legend():
    """22歳 通算14本 → 往年の大砲の22歳時点 (13本) 超え、 次は現役の壁 (34本)。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 6, 12, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cache = _young_cache("2004年1月1日", [
        {"年度": "2024", "本塁打": "6"}, {"年度": "2025", "本塁打": "8"}])
    out = angles.build_legend_age_compare_candidates(
        "", now=now, career_cache=cache, legends=_LEGENDS_FIXTURE,
        with_image=False)
    assert len(out) == 1
    c = out[0]
    assert c.focus_player == "若手太郎"
    assert "【若手太郎】22歳シーズン時点 通算14本塁打" in c.post_text
    assert "往年の大砲の22歳時点は13本" in c.post_text
    assert "次は現役の壁の22歳時点 34本" in c.post_text
    assert c.signature == "legend_compare|若手太郎|22|14"


def test_legend_compare_surprise_gate():
    """誰の同年齢時点も超えない (12本 < 13本) → 候補なし。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 6, 12, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cache = _young_cache("2004年1月1日", [{"年度": "2025", "本塁打": "12"}])
    assert angles.build_legend_age_compare_candidates(
        "", now=now, career_cache=cache, legends=_LEGENDS_FIXTURE,
        with_image=False) == []


def test_legend_compare_age_and_floor_gates():
    """max_age 超え / min_career_hr 未満は対象外。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 6, 12, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    old = _young_cache("1995年1月1日", [{"年度": "2025", "本塁打": "40"}])
    assert angles.build_legend_age_compare_candidates(
        "", now=now, career_cache=old, legends=_LEGENDS_FIXTURE,
        with_image=False) == []
    rookie = _young_cache("2005年1月1日", [{"年度": "2025", "本塁打": "3"}])
    assert angles.build_legend_age_compare_candidates(
        "", now=now, career_cache=rookie, legends=_LEGENDS_FIXTURE,
        with_image=False) == []


def test_legend_compare_adds_current_season_from_db(tmp_path):
    """今季分は insight.db atbats_json から加算 (career page 今季行は使わない)。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    db = tmp_path / "season.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE batting_logs (
            game_id TEXT, team_role TEXT, team_name TEXT,
            player_canonical TEXT, AB INT, H INT, RBI INT, R INT,
            atbats_json TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?,?,?)",
        ("g1", "giants", "巨人", "若手太郎", 4, 2, 2, 1,
         '["右越本①", "中越本②", "三 振", "遊ゴロ"]'),
    )
    conn.commit()
    conn.close()
    now = datetime(2026, 6, 12, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    # 過去 12 本 + 今季 DB 2 本 = 14 本 → 13 本超え
    cache = _young_cache("2004年1月1日", [
        {"年度": "2025", "本塁打": "12"},
        {"年度": "2026", "本塁打": "9"},  # 今季行は無視されること (二重計上防止)
    ])
    out = angles.build_legend_age_compare_candidates(
        str(db), now=now, career_cache=cache, legends=_LEGENDS_FIXTURE,
        with_image=False)
    assert len(out) == 1
    assert "通算14本塁打" in out[0].post_text


def test_legend_compare_excludes_self():
    """現役レジェンド本人 (同名) は比較対象から除外。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 6, 12, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    legends = {
        "若手太郎": {"npb_id": "999", "birthdate": "2004年1月1日",
                  "seasons": [{"年度": "2025", "本塁打": "8"}]},
    }
    cache = _young_cache("2004年1月1日", [{"年度": "2025", "本塁打": "8"}])
    assert angles.build_legend_age_compare_candidates(
        "", now=now, career_cache=cache, legends=legends,
        with_image=False) == []
