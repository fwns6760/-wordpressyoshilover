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


def test_opponent_split_compares_against_other_cards(tmp_path):
    """対戦別splitはシーズン平均ではなく、当該カード以外との比較にする。"""
    db = tmp_path / "opp_other.db"
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
    # 対阪神: 10安打/25打数 .400。その他: 10安打/50打数 .200。
    for i in range(5):
        gid = f"2026-05-{i + 1:02d}:g-t"
        conn.execute("INSERT INTO games VALUES (?,?,?,?,0,0)", (gid, f"2026-05-{i + 1:02d}", "阪神", "win"))
        conn.execute("INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?)", (gid, "giants", "巨人", "精度選手", 5, 2, 1))
    for i in range(10):
        gid = f"2026-05-{i + 6:02d}:g-c"
        conn.execute("INSERT INTO games VALUES (?,?,?,?,0,0)", (gid, f"2026-05-{i + 6:02d}", "広島", "loss"))
        conn.execute("INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?)", (gid, "giants", "巨人", "精度選手", 5, 1, 0))
    conn.commit()
    conn.close()

    out = angles.build_opponent_split_candidates(
        str(db), max_count=1, min_opp_ab=25, min_season_ab=75,
        min_other_ab=50, min_gap=0.120, with_image=False,
    )
    assert len(out) == 1
    c = out[0]
    assert "他カード .200" in c.post_text
    assert "差 +.200" in c.db_fact_line
    assert "シーズン" not in c.post_text


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


# ─── あの日の巨人 (on this day) ──────────────────────────────────────


_OTD_EVENTS = {
    "06-25": [{"year": 1959, "text": "プロ野球史上唯一の天覧試合", "source": "https://example.com"}],
}
_OTD_LEGENDS = {
    "order": ["大物レジェンド", "中堅レジェンド"],
    "stats": {
        "大物レジェンド": {"birth": "1936-02-20",
                     "npb": {"games": 2186, "hr": 444, "avg": ".305"}},
        "中堅レジェンド": {"birth": "1950-02-20", "npb": {"games": 800}},
    },
}


def _otd(now_md, **kw):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    m, d = now_md
    now = datetime(2026, m, d, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    return angles.build_on_this_day_candidates(
        now=now, events=_OTD_EVENTS, legends=_OTD_LEGENDS, **kw)


def test_on_this_day_event_first():
    out = _otd((6, 25))
    assert len(out) == 1
    c = out[0]
    assert "【6月25日】1959年のきょう" in c.post_text
    assert "天覧試合" in c.post_text
    assert c.signature == "on_this_day|06-25|1959"


def test_on_this_day_birthday_fallback_order_first():
    """イベント無し日は誕生日 fallback、 order 上位 (大物) を採用、 年齢は出さない。"""
    out = _otd((2, 20))
    assert len(out) == 1
    c = out[0]
    assert "【2月20日】1936年、大物レジェンドが生まれた日" in c.post_text
    assert "通算2186試合・444本塁打・打率.305" in c.post_text
    assert "歳" not in c.post_text and "誕生日" not in c.post_text
    assert c.signature == "on_this_day|02-20|birth|大物レジェンド"


def test_on_this_day_empty_when_no_match():
    assert _otd((1, 31)) == []


def test_on_this_day_respects_dedup():
    assert _otd((6, 25), dedup_set={"on_this_day|06-25|1959"}) == []


# ─── 試合前見どころ (今日の試合プレビュー) ───────────────────────────


def _pregame_db(tmp_path: Path) -> str:
    db = tmp_path / "pregame.db"
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
        CREATE TABLE pitching_logs (
            game_id TEXT, team_role TEXT, team_name TEXT,
            player_canonical TEXT, appearance_order INT, result_mark TEXT,
            K INT, IP REAL, ER INT
        );
        """
    )
    for i in range(4):
        gid = f"2026-05-{i + 1:02d}:g"
        conn.execute("INSERT INTO games VALUES (?,?,?,?,0,0)",
                     (gid, f"2026-05-{i + 1:02d}", "阪神" if i < 3 else "広島", "win"))
        conn.execute("INSERT INTO pitching_logs VALUES (?,?,?,?,?,?,?,?,?)",
                     (gid, "giants", "巨人", "剛腕太郎", 1,
                      "○" if i < 2 else "●", 7, 6.0, 2))
        conn.execute("INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?)",
                     (gid, "giants", "巨人", "好打者", 4, 2, 1))
    conn.commit()
    conn.close()
    return str(db)


def _pregame_now(hour=13):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime(2026, 6, 12, hour, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


_TODAY_GAME = [{"date": "2026-06-12", "opp": "阪神", "home_away": "本拠地",
                "time": "18:00", "place": "東京ドーム",
                "starter_g": "剛腕太郎", "starter_o": "敵軍投手"}]


def test_pregame_preview_builds_with_starter_and_keyman(tmp_path):
    db = _pregame_db(tmp_path)
    out = angles.build_pregame_preview_candidates(
        db, now=_pregame_now(), upcoming_fn=lambda: list(_TODAY_GAME))
    assert len(out) == 1
    p = out[0].post_text
    assert "【今日の巨人 vs 阪神 (東京ドーム 18:00)】" in p
    assert "予告先発 剛腕太郎 vs 敵軍投手" in p
    assert "今季4先発 2勝2敗・防御率3.00・28奪三振" in p
    assert "対阪神 今季2勝1敗" in p
    assert "対阪神キーマン 好打者: 打率.500" in p
    # 2026-07-03: am/pm slot 付き署名 (午後便でも 1 回再掲できる)
    assert out[0].signature == "pregame|2026-06-12|阪神|pm"


def test_pregame_preview_reappears_in_pm_slot(tmp_path):
    """朝便で出た後も、午後便 (12時以降) では別署名で再掲される。"""
    db = _pregame_db(tmp_path)
    dedup: set = set()
    am = angles.build_pregame_preview_candidates(
        db, now=_pregame_now(hour=9), upcoming_fn=lambda: list(_TODAY_GAME),
        dedup_set=dedup)
    assert len(am) == 1 and am[0].signature.endswith("|am")
    dedup.add(am[0].signature)
    # 同じ午前はもう出ない
    assert angles.build_pregame_preview_candidates(
        db, now=_pregame_now(hour=10), upcoming_fn=lambda: list(_TODAY_GAME),
        dedup_set=dedup) == []
    # 午後は再掲される
    pm = angles.build_pregame_preview_candidates(
        db, now=_pregame_now(hour=15), upcoming_fn=lambda: list(_TODAY_GAME),
        dedup_set=dedup)
    assert len(pm) == 1 and pm[0].signature.endswith("|pm")


def test_pregame_preview_gates(tmp_path):
    db = _pregame_db(tmp_path)
    # 今日の試合でない
    other = [dict(_TODAY_GAME[0], date="2026-06-13")]
    assert angles.build_pregame_preview_candidates(
        db, now=_pregame_now(), upcoming_fn=lambda: other) == []
    # 試合開始後
    assert angles.build_pregame_preview_candidates(
        db, now=_pregame_now(hour=19), upcoming_fn=lambda: list(_TODAY_GAME)) == []
    # 日程取得失敗 → graceful 空
    assert angles.build_pregame_preview_candidates(
        db, now=_pregame_now(), upcoming_fn=lambda: []) == []


def test_pregame_preview_no_numbers_no_post(tmp_path):
    """数字が 1 つも作れない時は出さない (埋め草禁止)。"""
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE games (game_id TEXT PRIMARY KEY, game_date TEXT, opponent TEXT,
            result TEXT, giants_score INT, opp_score INT);
        CREATE TABLE batting_logs (game_id TEXT, team_role TEXT, team_name TEXT,
            player_canonical TEXT, AB INT, H INT, RBI INT);
        CREATE TABLE pitching_logs (game_id TEXT, team_role TEXT, team_name TEXT,
            player_canonical TEXT, appearance_order INT, result_mark TEXT,
            K INT, IP REAL, ER INT);
        """
    )
    conn.commit()
    conn.close()
    assert angles.build_pregame_preview_candidates(
        str(db), now=_pregame_now(), upcoming_fn=lambda: list(_TODAY_GAME)) == []


def test_opp_split_opponents_filter(tmp_path):
    db = _make_db(tmp_path)
    base = angles.build_opponent_split_candidates(
        db, max_count=2, min_opp_ab=5, min_season_ab=10, min_gap=0.0,
        with_image=False)
    assert base  # filter なしでは候補あり
    only_hiroshima = angles.build_opponent_split_candidates(
        db, max_count=2, min_opp_ab=5, min_season_ab=10, min_gap=0.0,
        with_image=False, opponents={"広島"})
    for c in only_hiroshima:
        assert "広島" in c.signature


# ─── 年俸コスパ (データ×年俸クロス) ──────────────────────────────────


def _salary_db(tmp_path: Path) -> str:
    db = tmp_path / "salary.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE batting_logs (
            game_id TEXT, team_role TEXT, team_name TEXT,
            player_canonical TEXT, AB INT, H INT, RBI INT
        );
        CREATE TABLE games (
            game_id TEXT PRIMARY KEY, game_date TEXT, opponent TEXT,
            result TEXT, giants_score INT, opp_score INT
        );
        """
    )
    # 3 選手: 安打20ずつ。 若手=400万 (単価20万)、 中堅=8000万、 主力=2億
    for i, (name, _sal) in enumerate(
            (("若手バーゲン", 400), ("中堅選手", 8000), ("高額主力", 20000))):
        for j in range(10):
            gid = f"g{i}-{j}"
            conn.execute(
                "INSERT OR IGNORE INTO games VALUES (?,?,?,?,0,0)",
                (gid, f"2026-05-{j + 1:02d}", "阪神", "win"))
            conn.execute(
                "INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?)",
                (gid, "giants", "巨人", name, 4, 2, 1))
    conn.commit()
    conn.close()
    return str(db)


_SALARY_MAP = {"若手バーゲン": 400, "中堅選手": 8000, "高額主力": 20000}


def test_salary_value_bargain_only():
    """単価がチーム中央値の半分未満の若手だけ出る。"""
    import pytest as _pytest
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tmp = Path(__import__("tempfile").mkdtemp())
    db = _salary_db(tmp)
    now = datetime(2026, 6, 12, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    out = angles.build_salary_value_candidates(
        db, now=now, salary_map=dict(_SALARY_MAP))
    assert len(out) == 1
    c = out[0]
    assert c.focus_player == "若手バーゲン"
    # 20安打 / 400万 = 単価20万、 中央値 = 8000/20 = 400万
    assert "1安打あたり約20万円" in c.post_text
    assert "推定年俸400万円" in c.post_text
    assert "高額主力" not in c.post_text  # 割高側は一切出さない
    assert c.signature == "salary_value|若手バーゲン|20"


def test_salary_value_gates():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tmp = Path(__import__("tempfile").mkdtemp())
    db = _salary_db(tmp)
    now = datetime(2026, 6, 12, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    # 年俸 map 空 → 0件
    assert angles.build_salary_value_candidates(db, now=now, salary_map={}) == []
    # 全員同単価 (中央値の半分未満が居ない) → 0件
    flat = {"若手バーゲン": 8000, "中堅選手": 8000, "高額主力": 8000}
    assert angles.build_salary_value_candidates(db, now=now, salary_map=flat) == []
    # 規定安打未満 → 対象外 (min_hits=25 > 20)
    assert angles.build_salary_value_candidates(
        db, now=now, salary_map=dict(_SALARY_MAP), min_hits=25) == []


# ─── chikupn型: 節目達成 / 今季初・以来 ─────────────────────────────


def _rarity_db(tmp_path: Path, *, with_event=True, cg=False) -> str:
    db = tmp_path / "rare.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE games (game_id TEXT PRIMARY KEY, game_date TEXT, opponent TEXT,
            result TEXT, giants_score INT, opp_score INT);
        CREATE TABLE batting_logs (game_id TEXT, team_role TEXT, team_name TEXT,
            player_canonical TEXT, AB INT, H INT, RBI INT, atbats_json TEXT);
        CREATE TABLE pitching_logs (game_id TEXT, team_role TEXT, team_name TEXT,
            player_canonical TEXT, appearance_order INT, result_mark TEXT,
            K INT, IP REAL, R INT, ER INT);
        CREATE TABLE inning_scores (game_id TEXT, team_role TEXT,
            inning_json TEXT, total INT);
        """
    )
    # 巨人戦 2 試合 + 他球団戦 1 試合 (混入チェック: 日付がより新しい)
    conn.execute("INSERT INTO games VALUES ('g1','2026-06-10','阪神','win',6,2)")
    conn.execute("INSERT INTO games VALUES ('g2','2026-06-11','阪神','win',8,1)")
    conn.execute("INSERT INTO games VALUES ('x1','2026-06-12','ロッテ','win',NULL,5)")
    aj_hr = '["右越本①", "中越本①", "左越本②", "三 振"]' if with_event else '["中前安","-","-","-"]'
    conn.execute("INSERT INTO batting_logs VALUES ('g1','giants','巨人','普通の日',4,1,0,'[\"中前安\"]')")
    conn.execute(f"INSERT INTO batting_logs VALUES ('g2','giants','巨人','大暴れ',4,3,3,'{aj_hr}')")
    conn.execute("INSERT INTO pitching_logs VALUES ('g2','giants','巨人','剛腕完投',1,'○',10,9.0,1,1)" if cg
                 else "INSERT INTO pitching_logs VALUES ('g2','giants','巨人','普通先発',1,'○',5,6.0,1,1)")
    conn.execute("INSERT INTO inning_scores VALUES ('g2','giants','[\"0\",\"6\",\"0\",\"2\",\"0\",\"0\",\"0\",\"0\",\"x\"]',8)")
    conn.commit()
    conn.close()
    return str(db)


def _rare_now():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime(2026, 6, 12, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def test_rarity_detects_giants_latest_game_only(tmp_path):
    """他球団戦 (6/12 ロッテ) でなく最新の巨人戦 (6/11 阪神) を対象にする。"""
    db = _rarity_db(tmp_path)
    out = angles.build_rarity_candidates(db, now=_rare_now(), max_count=3)
    assert out
    assert all("ロッテ" not in c.post_text for c in out)
    assert any("1試合3本塁打！" in c.post_text and "今季初" in c.post_text
               and "阪神" in c.post_text for c in out)
    assert any("1イニング6得点！" in c.post_text for c in out)


def test_rarity_complete_game_since(tmp_path):
    db = _rarity_db(tmp_path, cg=True)
    rotation = [{"year": 2025, "games": [
        {"date": "09月15日", "pitcher": "往年エース", "ip": "9", "runs": "2"}]}]
    out = angles.build_rarity_candidates(
        db, now=_rare_now(), max_count=5, rotation_years=rotation)
    cg = [c for c in out if "完投！" in c.post_text]
    assert cg and "2025年09月15日 往年エース以来" in cg[0].post_text
    assert "9回10奪三振1失点" in cg[0].post_text


def test_rarity_no_event_no_post(tmp_path):
    db = _rarity_db(tmp_path, with_event=False)
    out = angles.build_rarity_candidates(db, now=_rare_now(), max_count=3)
    assert all("本塁打" not in c.post_text for c in out)


def test_rarity_stale_db_silent(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    db = _rarity_db(tmp_path)
    later = datetime(2026, 6, 20, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert angles.build_rarity_candidates(db, now=later, max_count=3) == []


def test_milestone_crossing_detected(tmp_path):
    """通算 98 + 直近試合 3 本 = 101 で 100号を跨ぐ。 跨がない選手は出ない。"""
    db = _rarity_db(tmp_path)
    cache = {
        "ids": {"大暴れ": "1", "普通の日": "2"},
        "players": {
            "1": {"batting": {"years": [{"年度": "2025", "本塁打": "98"}]}},
            "2": {"batting": {"years": [{"年度": "2025", "本塁打": "10"}]}},
        },
    }
    out = angles.build_milestone_candidates(
        db, now=_rare_now(), career_cache=cache)
    assert len(out) == 1
    c = out[0]
    assert c.focus_player == "大暴れ"
    assert "【巨人】大暴れ　NPB通算100本 達成！" in c.post_text
    assert "通算101本" in c.post_text and "今季3本" in c.post_text
    assert c.signature == "milestone|大暴れ|本塁打|100"


def test_milestone_no_crossing_no_post(tmp_path):
    db = _rarity_db(tmp_path)
    cache = {"ids": {"大暴れ": "1"}, "players": {"1": {"batting": {"years": [
        {"年度": "2025", "本塁打": "50"}]}}}}
    assert angles.build_milestone_candidates(
        db, now=_rare_now(), career_cache=cache) == []


# ─── 登録抹消速報 (Tigers型) ─────────────────────────────────────────


def _moves_payload(year=2026):
    return {"year": year, "moves": [
        {"date": "6/12", "reg": ["新戦力"], "out": ["故障 太郎"]},
        {"date": "6/8", "reg": [], "out": ["過去の人"]},
    ]}


def test_roster_move_today(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 6, 12, 13, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    out = angles.build_roster_move_candidates(
        now=now, moves_fn=lambda y: _moves_payload(y))
    assert len(out) == 1
    c = out[0]
    assert "【巨人】6/12 出場選手登録・抹消" in c.post_text
    assert "登録: 新戦力" in c.post_text and "抹消: 故障太郎" in c.post_text
    assert "過去の人" not in c.post_text  # 古い公示は出さない
    assert c.signature == "roster|2026|6/12|故障太郎,新戦力"


def test_roster_move_no_recent_no_post():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 6, 20, 13, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert angles.build_roster_move_candidates(
        now=now, moves_fn=lambda y: _moves_payload(y)) == []


def test_roster_move_dedup():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 6, 12, 13, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert angles.build_roster_move_candidates(
        now=now, moves_fn=lambda y: _moves_payload(y),
        dedup_set={"roster|2026|6/12|故障太郎,新戦力"}) == []


# ─── 今フック (now-context) 優先選定 (2026-07-03) ─────────────────────


def _ctx_db(tmp_path: Path) -> str:
    db = tmp_path / "ctx.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE games (game_id TEXT PRIMARY KEY, game_date TEXT, opponent TEXT,
            result TEXT, giants_score INT, opp_score INT);
        CREATE TABLE batting_logs (game_id TEXT, team_role TEXT, team_name TEXT,
            player_canonical TEXT, AB INT, H INT, RBI INT);
        CREATE TABLE pitching_logs (game_id TEXT, team_role TEXT, team_name TEXT,
            player_canonical TEXT, appearance_order INT, result_mark TEXT,
            K INT, IP REAL, ER INT);
        """
    )
    gid = "2026-07-02:g"
    conn.execute("INSERT INTO games VALUES (?,?,?,?,0,0)",
                 (gid, "2026-07-02", "ヤクルト", "win"))
    conn.execute("INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?)",
                 (gid, "giants", "巨人", "好打者", 4, 3, 1))
    conn.execute("INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?)",
                 (gid, "giants", "巨人", "凡退者", 4, 0, 0))
    conn.execute("INSERT INTO pitching_logs VALUES (?,?,?,?,?,?,?,?,?)",
                 (gid, "giants", "巨人", "先発好投", 1, "○", 8, 7.0, 1))
    conn.commit()
    conn.close()
    return str(db)


def _ctx_now():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime(2026, 7, 3, 13, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def test_now_context_hooks_sources_and_precedence(tmp_path):
    db = _ctx_db(tmp_path)
    hooks = angles.build_now_context_hooks(
        db,
        now=_ctx_now(),
        lineup_focus_names=["好打者"],  # 昨日3安打だがスタメンが上書き (score 3)
        topical_counts={"話題選手": 2, "単発言及": 1},
    )
    assert hooks["好打者"] == ("今日のスタメン", 3)
    assert hooks["先発好投"] == ("昨日先発7回1失点", 2)
    assert hooks["話題選手"][1] == 1
    assert "単発言及" not in hooks  # topical_min=2 未満
    assert "凡退者" not in hooks  # 昨日出場のみでは hook にならない


def test_now_context_hooks_stale_game_ignored(tmp_path):
    """直近試合が一昨日以前なら last-game hook は付かない。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    db = _ctx_db(tmp_path)
    hooks = angles.build_now_context_hooks(
        db, now=datetime(2026, 7, 5, 13, 0, tzinfo=ZoneInfo("Asia/Tokyo")))
    assert "好打者" not in hooks


def test_now_context_priority_orders_and_caps(tmp_path):
    from types import SimpleNamespace as NS
    hooks = {"好打者": ("昨日3安打", 2), "スタメン男": ("今日のスタメン", 3)}
    # 2026-07-14: x_buzz_post (巨人動画引用RT) は inherent now 扱いへ変更 (score 1)。
    # 文脈ゼロの cap 対象は「フック無し選手のデータ角度」等の非 inherent metric。
    cands = [
        NS(metric="データ角度", focus_player="フック無しA", why_now=""),
        NS(metric="データ角度", focus_player="フック無しB", why_now=""),
        NS(metric="データ角度", focus_player="フック無しC", why_now=""),
        NS(metric="x_buzz_post", focus_player="好打者", why_now="動画"),
        NS(metric="試合前見どころ", focus_player="", why_now="今日の試合"),
        NS(metric="NEWS_OPINION", focus_player="ニュース選手", why_now=""),
        NS(metric="x_buzz_post", focus_player="動画男", why_now=""),
        NS(metric="x_buzz_post", focus_player="スタメン男", why_now=""),
    ]
    out = angles.apply_now_context_priority(cands, hooks, non_context_max=2, min_keep=3)
    # 文脈スコア降順 (同スコアは入力順の stable sort):
    # 見どころ(3) → スタメン(3) → 好打者(2) → ニュース/動画男(1) → 文脈ゼロは2件まで
    players = [c.focus_player or c.metric for c in out]
    assert players[:2] == ["試合前見どころ", "スタメン男"]
    assert players[2] == "好打者"
    # フック無しの巨人動画引用RT (動画男) は inherent now (score 1) で cap に飲まれない
    assert "動画男" in players
    assert len([p for p in players if p.startswith("フック無し")]) == 2
    assert len(out) == 7
    # why_now にフックが前置される (選手フック由来のみ)
    assert out[1].why_now.startswith("⏰今日のスタメン")
    assert "⏰昨日3安打" in out[2].why_now


def test_now_context_priority_no_context_unchanged():
    from types import SimpleNamespace as NS
    cands = [
        NS(metric="x_buzz_post", focus_player="A", why_now=""),
        NS(metric="x_buzz_post", focus_player="B", why_now=""),
    ]
    out = angles.apply_now_context_priority(cands, {}, non_context_max=1)
    assert out == cands  # 文脈ありゼロの便は件数・並びとも不変


def test_now_context_priority_min_keep_protects_mail():
    from types import SimpleNamespace as NS
    hooks = {"文脈男": ("今日のスタメン", 3)}
    cands = [
        NS(metric="x_buzz_post", focus_player="文脈男", why_now=""),
        NS(metric="x_buzz_post", focus_player="ゼロ1", why_now=""),
        NS(metric="x_buzz_post", focus_player="ゼロ2", why_now=""),
    ]
    out = angles.apply_now_context_priority(cands, hooks, non_context_max=0, min_keep=3)
    assert len(out) == 3  # min_keep がメールを枯らさない
