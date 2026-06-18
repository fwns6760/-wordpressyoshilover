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
