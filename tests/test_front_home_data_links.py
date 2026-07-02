"""Static checks for the front page data hub links."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "src" / "yoshilover-063-frontend.php"
CUSTOM_CSS = ROOT / "src" / "custom.css"


def test_home_data_hub_links_to_draft_topic_cluster() -> None:
    # 2026-07-02: 0.23.x 現状 (2グループ化・trailing slash 無し) に同期し、
    # 歴代選手・レジェンド導線 (user 指摘「トップから歴代選手の導線がない」) を追加。
    src = PLUGIN.read_text(encoding="utf-8")
    assert "Version: 0.23.9" in src
    assert "'t' => '打撃成績ランキング'" in src
    assert "'href' => '/data/batting-ranking'" in src
    assert "'t' => '投手成績ランキング'" in src
    assert "'href' => '/data/pitching-ranking'" in src
    assert "'t' => '選手別 個人成績'" in src
    assert "'href' => '/data#ys-player-search'" in src
    assert "'t' => '歴代選手・レジェンド'" in src
    assert "'href' => '/data/record'" in src
    assert "'s' => '王貞治・長嶋茂雄・松井秀喜ら歴代名鑑'" in src
    assert "'t' => '歴代ドラフト'" in src
    assert "'href' => '/data/draft'" in src
    assert "'t' => '2軍試合日程・結果'" in src
    assert "'href' => '/data/farm'" in src
    assert "'t' => '歴代背番号'" in src
    assert "'href' => '/data/jersey-numbers'" in src
    assert "'t' => '注目データ'" in src
    assert "'href' => '/data/notable'" in src
    assert "'t' => '先発ローテ一覧'" in src
    assert "'href' => '/data/rotation'" in src
    assert "'t' => '出場選手登録・抹消'" in src
    assert "'href' => '/data/roster-moves'" in src
    assert "'t' => 'チケット情報'" in src
    assert "'href' => '/data/tickets'" in src
    assert "'t' => 'オープン戦結果'" in src
    assert "'href' => '/data/open-games'" in src
    assert "'t' => '驚き・注目選手'" not in src
    assert "'t' => '今日の注目選手'" not in src


def test_home_data_hub_does_not_render_rotation_table_section() -> None:
    # 2026-06-09: user 指示でトップの大きな「先発ローテ一覧（2007年〜2026年）」表
    # セクションを廃止。先発ローテはデータグリッドのカード → /data/rotation で提供。
    src = PLUGIN.read_text(encoding="utf-8")
    # 外部 fetch / 出典 は完全撤去 (旧ライブ scrape 実装の名残なし)
    assert "my-favorite-giants.net" not in src
    assert "出典を見る" not in src
    # トップの大きな表セクションはレンダリングしない (関数は残るが呼び出しゼロ)
    assert src.count("yoshilover_063_render_home_starter_rotation_table()") == 1  # 定義のみ
    # データグリッドのカードは /data/rotation へ残す
    assert "'t' => '先発ローテ一覧'" in src
    assert "'href' => '/data/rotation'" in src


def test_frontend_removes_legacy_jersey_toplink_widget() -> None:
    src = PLUGIN.read_text(encoding="utf-8")
    assert "function yoshilover_063_remove_legacy_jersey_toplink_widget" in src
    assert "yoshi-jersey-toplink" in src
    assert "巨人 歴代背番号・永久欠番を見る" in src


def test_frontend_does_not_inject_visible_header_logo_copy() -> None:
    src = PLUGIN.read_text(encoding="utf-8")
    assert "yoshi-headLogo__text" not in src
    assert "yoshi-headLogo__subtitle" not in src
    assert "読売ジャイアンツ専門の速報＆データサイト｜試合結果" not in src


def test_custom_css_does_not_style_removed_header_logo_copy() -> None:
    src = CUSTOM_CSS.read_text(encoding="utf-8")
    assert "yoshi-headLogo__text" not in src
    assert "yoshi-headLogo__subtitle" not in src
    assert "H1 (c-headLogo) 内に real DOM" not in src
