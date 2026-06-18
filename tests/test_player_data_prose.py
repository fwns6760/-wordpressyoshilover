"""player_data_prose の決定的解説文生成の検証(数字は split 由来のみ)。"""

from types import SimpleNamespace

from src import player_data_prose as pdp


def _player(**kw):
    base = dict(
        name="坂本勇人", season_avg=0.255, season_games=62, season_hr=8, season_rbi=36,
        venue_split_stats=[("本拠地", 30, 110, 33, 18, 0.300),
                           ("ビジター", 32, 106, 22, 18, 0.208)],
        vs_lr_split_stats=[("対左", 60, 18, 0.300), ("対右", 156, 37, 0.237)],
        risp_split_stats=[("得点圏", 50, 16, 0.320)],
        month_split_stats=[("5月", 25, 90, 30, 0.333), ("6月", 20, 70, 14, 0.200)],
        opponent_split_stats=[("中日", 12, 40, 15, 5, 0.375), ("阪神", 12, 44, 8, 3, 0.182)],
        hit_streak_active=4,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_prose_uses_only_split_numbers():
    html = pdp.build_player_prose(_player())
    assert "坂本勇人" in html
    assert "打率.255" in html              # season avg
    assert "本拠地では打率.300" in html      # venue
    assert "ビジターでは.208" in html
    assert "対左投手は打率.300" in html      # L/R
    assert "得点圏打率は.320" in html        # RISP
    assert "5月" in html and ".333" in html  # best month
    assert "中日" in html and ".375" in html  # best opponent
    assert "4試合連続安打" in html           # streak


def test_prose_giants_strength_phrasing():
    html = pdp.build_player_prose(_player())
    assert "本拠地に強く" in html   # home .300 > away .208
    assert "左投手に強い" in html   # 左.300 > 右.237


def test_prose_empty_when_thin_data():
    # split が無くシーズンだけ → 文章 1 つ未満 → 空
    p = SimpleNamespace(name="新人", season_avg=None, season_games=0)
    assert pdp.build_player_prose(p) == ""


def test_prose_no_name_returns_empty():
    assert pdp.build_player_prose(SimpleNamespace(name="")) == ""


def test_avg_format():
    assert pdp._avg(0.359) == ".359"
    assert pdp._avg(1.107) == "1.107"
    assert pdp._avg(None) == ""


def test_prose_covers_more_dimensions_and_weak_opponent():
    p = _player(
        weekday_split_stats=[("日", 8, 30, 12, 0.400), ("月", 5, 18, 3, 0.167)],
        lineup_slot_stats=[(3, 40, 150, 45, 30, 0.300), (5, 10, 30, 6, 4, 0.200)],
        inning_split_stats=[("序盤", 80, 28, 0.350), ("終盤", 70, 14, 0.200)],
        interleague_split_stats=[("交流戦", 18, 60, 21, 0.350), ("リーグ戦", 44, 156, 35, 0.224)],
    )
    html = pdp.build_player_prose(p)
    assert "日に打率.400" in html          # 曜日別
    assert "3番で打率.300" in html         # 打順別
    assert "序盤に打率.350" in html        # 序中終盤
    assert "交流戦では打率.350" in html      # 交流戦
    assert "苦手" in html or "苦戦" in html  # 相手別の弱点も書く
    assert "阪神戦は.182" in html           # weak opponent


def test_pitcher_prose():
    pit = SimpleNamespace(
        name="戸郷翔征", season_avg=None, season_games=0,
        pitch_games=12, pitch_wins=6, pitch_losses=4, pitch_ip=80.0, pitch_k=85,
        pitch_era=2.50, pitch_whip=1.05, pitch_k_per_9=9.5,
        pitch_opponent_split_stats=[("中日", 3, 21.0, 12, 5, 1.20),
                                    ("阪神", 3, 18.0, 20, 8, 4.50)],
        pitch_venue_split_stats=[("本拠地", 6, 40.0, 30, 10, 2.00),
                                 ("ビジター", 6, 40.0, 35, 15, 3.00)],
    )
    html = pdp.build_player_prose(pit)
    assert "戸郷翔征" in html
    assert "防御率2.50" in html
    assert "中日戦で防御率1.20" in html   # 抑えた相手
    assert "阪神戦は4.50" in html         # 打たれた相手
    assert "本拠地では防御率2.00" in html
