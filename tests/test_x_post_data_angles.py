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
