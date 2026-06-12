"""巨人 年俸コスパ分析ページ (1ページ完結) のテンプレート。

データ×年俸クロス (2026-06-12 user GO「他のページにないなら良い。
低品質だとSEOに弱くなる」「一ページに収まるくらいなら」)。

- 切り口: 「1安打あたりの推定年俸」「1奪三振あたりの推定年俸」(SERP 確認済みで
  競合ゼロ)。普通の年俸ランキングは /data/salary/ (年俸一覧) の担当で、 ここでは
  重複させない。
- 品質基準 (受け入れ条件): ①毎朝自動更新+更新日明示 ②算出方法・読み方の解説本文
  ③/data/salary/<slug>/ への内部リンク ④独自切り口限定 ⑤データが薄い時期
  (規定到達者 < _MIN_ROWS) は publish 側が skip して低品質のまま出さない。
- データ源: config/giants_salary.json (検証済 baked) × insight.db 今季集計。
  LLM 不使用。
"""
from __future__ import annotations

import json as _json
import sqlite3 as _sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.data_site_internal_link import breadcrumb_jsonld
from src.data_site_related_links import dataset_jsonld

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data"
SALARY_URL = "https://yoshilover.com/data/salary"
SLUG = "salary-value"
JST = ZoneInfo("Asia/Tokyo")

_MIN_HITS = 20      # 野手の規定 (今季安打)
_MIN_K = 20         # 投手の規定 (今季奪三振)
_MIN_ROWS = 5       # これ未満なら「薄い」として publish しない


def _esc(t) -> str:
    import html as _html
    return _html.escape(str(t if t is not None else ""))


def _norm(s: str) -> str:
    return str(s or "").replace("　", "").replace(" ", "")


def _fmt3(v: float) -> str:
    return f"{v:.3f}".lstrip("0") if v < 1 else f"{v:.3f}"


def _sal_disp(man: int) -> str:
    if man >= 10000:
        oku = man / 10000
        return (f"{oku:.1f}".rstrip("0").rstrip(".")) + "億円"
    return f"{man:,}万円"


def load_salary_value_data(
    db_path: str,
    salary_json_path: str | None = None,
    *,
    now: datetime | None = None,
) -> dict:
    """salary json × insight.db を join して表データを作る (純粋寄り、 test 可)。"""
    if now is None:
        now = datetime.now(JST)
    if salary_json_path is None:
        salary_json_path = str(
            Path(__file__).resolve().parent.parent / "config" / "giants_salary.json")
    try:
        sal_raw = _json.loads(Path(salary_json_path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    salary: dict[str, tuple[int, str]] = {}  # 正規化名 -> (2026年俸万円, slug)
    for p in sal_raw.get("players") or []:
        if not p.get("active"):
            continue
        for y in p.get("years") or []:
            if y.get("year") == 2026 and y.get("team") == "巨人" and y.get("salary_man"):
                salary[_norm(p.get("name") or "")] = (
                    int(y["salary_man"]), str(p.get("slug") or ""))
                break
    if not salary:
        return {}

    batters: list[dict] = []
    pitchers: list[dict] = []
    try:
        with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            for canon, ab, h, rbi in conn.execute(
                "SELECT player_canonical, SUM(COALESCE(AB,0)), SUM(COALESCE(H,0)), "
                " SUM(COALESCE(RBI,0)) FROM batting_logs WHERE team_name='巨人' "
                " AND player_canonical IS NOT NULL GROUP BY player_canonical",
            ):
                h, ab, rbi = int(h or 0), int(ab or 0), int(rbi or 0)
                sal = salary.get(_norm(canon))
                if h < _MIN_HITS or not sal:
                    continue
                batters.append({
                    "name": canon, "slug": sal[1], "salary_man": sal[0],
                    "h": h, "ab": ab, "rbi": rbi,
                    "avg": h / ab if ab else 0.0, "unit": sal[0] / h,
                })
            for canon, n, k, ip in conn.execute(
                "SELECT player_canonical, COUNT(*), SUM(COALESCE(K,0)), "
                " SUM(COALESCE(IP,0)) FROM pitching_logs WHERE team_name='巨人' "
                " AND player_canonical IS NOT NULL GROUP BY player_canonical",
            ):
                k, n = int(k or 0), int(n or 0)
                sal = salary.get(_norm(canon))
                if k < _MIN_K or not sal:
                    continue
                pitchers.append({
                    "name": canon, "slug": sal[1], "salary_man": sal[0],
                    "k": k, "games": n, "ip": float(ip or 0),
                    "unit": sal[0] / k,
                })
    except Exception:  # noqa: BLE001
        return {}
    batters.sort(key=lambda r: r["unit"])
    pitchers.sort(key=lambda r: r["unit"])
    return {
        "updated": now.strftime("%Y-%m-%d %H:%M JST"),
        "year": now.year,
        "batters": batters,
        "pitchers": pitchers,
    }


def is_thin(data: dict) -> bool:
    """規定到達者が少なすぎる時 True (publish skip = 低品質のまま出さない)。"""
    return len((data or {}).get("batters") or []) < _MIN_ROWS


def render_salary_value_title(data: dict) -> str:
    return f"巨人 年俸コスパ分析 {data.get('year', '')}｜1安打あたりの推定年俸で見る割安選手ランキング"


def render_salary_value_excerpt(data: dict) -> str:
    b = (data.get("batters") or [])
    top = b[0]["name"] if b else ""
    return (
        f"読売ジャイアンツの{data.get('year')}年推定年俸と今季成績を掛け合わせ、"
        f"「1安打あたりの年俸」「1奪三振あたりの年俸」で割安選手を割り出す独自分析。"
        + (f"現在の最割安は{top}。" if top else "")
        + "毎朝自動更新。"
    )


def _player_link(name: str, slug: str) -> str:
    if slug:
        return f'<a href="{SALARY_URL}/{_esc(slug)}/">{_esc(name)}</a>'
    return _esc(name)


def _batter_table(rows: list[dict], median_unit: float) -> str:
    head = (
        '<div style="overflow-x:auto;"><table style="font-size:13px;border-collapse:collapse;min-width:560px;">'
        "<tr style='background:#f5f5f5;'>"
        "<th style='padding:4px 8px;'>#</th><th style='padding:4px 8px;text-align:left;'>選手</th>"
        "<th style='padding:4px 8px;'>安打</th><th style='padding:4px 8px;'>打率</th>"
        "<th style='padding:4px 8px;'>打点</th><th style='padding:4px 8px;'>推定年俸</th>"
        "<th style='padding:4px 8px;'>1安打あたり</th><th style='padding:4px 8px;'>中央値比</th></tr>"
    )
    trs = []
    for i, r in enumerate(rows, 1):
        ratio = r["unit"] / median_unit if median_unit else 0
        hl = " background:#fff8e6;" if ratio < 0.5 else ""
        trs.append(
            f"<tr style='border-bottom:1px solid #eee;{hl}'>"
            f"<td style='padding:4px 8px;text-align:center;'>{i}</td>"
            f"<td style='padding:4px 8px;'>{_player_link(r['name'], r['slug'])}</td>"
            f"<td style='padding:4px 8px;text-align:right;'>{r['h']}</td>"
            f"<td style='padding:4px 8px;text-align:right;'>{_fmt3(r['avg'])}</td>"
            f"<td style='padding:4px 8px;text-align:right;'>{r['rbi']}</td>"
            f"<td style='padding:4px 8px;text-align:right;'>{_sal_disp(r['salary_man'])}</td>"
            f"<td style='padding:4px 8px;text-align:right;'><b>約{r['unit']:,.0f}万円</b></td>"
            f"<td style='padding:4px 8px;text-align:right;'>{ratio:.2f}倍</td></tr>"
        )
    return head + "".join(trs) + "</table></div>"


def _pitcher_table(rows: list[dict], median_unit: float) -> str:
    head = (
        '<div style="overflow-x:auto;"><table style="font-size:13px;border-collapse:collapse;min-width:520px;">'
        "<tr style='background:#f5f5f5;'>"
        "<th style='padding:4px 8px;'>#</th><th style='padding:4px 8px;text-align:left;'>投手</th>"
        "<th style='padding:4px 8px;'>奪三振</th><th style='padding:4px 8px;'>登板</th>"
        "<th style='padding:4px 8px;'>投球回</th><th style='padding:4px 8px;'>推定年俸</th>"
        "<th style='padding:4px 8px;'>1奪三振あたり</th></tr>"
    )
    trs = []
    for i, r in enumerate(rows, 1):
        ratio = r["unit"] / median_unit if median_unit else 0
        hl = " background:#fff8e6;" if ratio < 0.5 else ""
        trs.append(
            f"<tr style='border-bottom:1px solid #eee;{hl}'>"
            f"<td style='padding:4px 8px;text-align:center;'>{i}</td>"
            f"<td style='padding:4px 8px;'>{_player_link(r['name'], r['slug'])}</td>"
            f"<td style='padding:4px 8px;text-align:right;'>{r['k']}</td>"
            f"<td style='padding:4px 8px;text-align:right;'>{r['games']}</td>"
            f"<td style='padding:4px 8px;text-align:right;'>{r['ip']:.1f}</td>"
            f"<td style='padding:4px 8px;text-align:right;'>{_sal_disp(r['salary_man'])}</td>"
            f"<td style='padding:4px 8px;text-align:right;'><b>約{r['unit']:,.0f}万円</b></td></tr>"
        )
    return head + "".join(trs) + "</table></div>"


def render_salary_value_html(data: dict) -> str:
    year = data.get("year")
    batters = data.get("batters") or []
    pitchers = data.get("pitchers") or []
    b_median = batters[len(batters) // 2]["unit"] if batters else 0.0
    p_median = pitchers[len(pitchers) // 2]["unit"] if pitchers else 0.0

    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › '
        f'<a href="{SALARY_URL}" style="color:#666;">年俸一覧</a> › <span>年俸コスパ分析</span></nav>'
    )
    # SSP og:description は本文先頭から生成されるため、 lead を最初に置く
    lead = (
        f'<h1 id="top" style="font-size:21px;margin:0 0 4px;">巨人 年俸コスパ分析 {year}'
        "（1安打あたりの推定年俸）</h1>"
        '<p style="font-size:13px;color:#444;margin:0 0 8px;line-height:1.7;">'
        f"読売ジャイアンツの{year}年推定年俸と今季成績を掛け合わせ、"
        "「<b>1安打あたりいくら払っているか</b>」「<b>1奪三振あたりいくらか</b>」という"
        "単価で選手を並べた独自分析です。単価が小さいほど、年俸に対して結果を多く出している"
        "「割安」な選手ということになります。よくある年俸ランキング（金額順）は"
        f'<a href="{SALARY_URL}/">年俸一覧ページ</a>に任せ、ここでは単価の切り口だけを扱います。</p>'
        f'<p style="font-size:12px;color:#888;margin:0 0 16px;">最終更新: {_esc(data.get("updated"))}'
        "（毎朝自動更新）｜年俸は報道ベースの推定値（出来高等は含まない場合があります）</p>"
    )
    how = (
        '<h2 style="font-size:17px;margin:20px 0 6px;">算出方法と読み方</h2>'
        '<ul style="font-size:13px;line-height:1.8;margin:0 0 12px;">'
        f"<li>野手: 今季<b>{_MIN_HITS}安打以上</b>を対象に「推定年俸 ÷ 今季安打数」を計算（万円/安打）。</li>"
        f"<li>投手: 今季<b>{_MIN_K}奪三振以上</b>を対象に「推定年俸 ÷ 今季奪三振数」を計算（万円/奪三振）。</li>"
        "<li>「中央値比」は対象選手の単価中央値に対する倍率。<b>0.5倍未満（=チーム標準の半分以下のコスト）を割安ゾーン</b>として色付けしています。</li>"
        "<li>若手は年俸が上がる前なので構造的に割安に出ます。逆に高年俸選手の単価が高いのは「割高」と言うより、実績への対価・期待値込みの契約だからです。"
        "このページは選手批判ではなく、<b>編成目線で「いま結果に対して支払いが軽い選手」を見つける</b>ための見方です。</li>"
        "<li>成績は NPB 公式の試合データ集計（insight.db）、年俸は出典付きで検証した推定値を使用しています。</li>"
        "</ul>"
    )
    b_sec = (
        f'<h2 style="font-size:17px;margin:20px 0 6px;">野手: 1安打あたりの推定年俸（単価が安い順）</h2>'
        + (_batter_table(batters, b_median) if batters else
           '<p style="color:#999;">対象選手のデータを準備中です。</p>')
        + (f'<p style="font-size:12px;color:#888;margin:6px 0 0;">対象{len(batters)}人 ｜ '
           f"単価中央値: 約{b_median:,.0f}万円/安打</p>" if batters else "")
    )
    p_sec = (
        f'<h2 style="font-size:17px;margin:20px 0 6px;">投手: 1奪三振あたりの推定年俸（単価が安い順）</h2>'
        + (_pitcher_table(pitchers, p_median) if pitchers else
           '<p style="color:#999;">対象投手のデータを準備中です。</p>')
        + (f'<p style="font-size:12px;color:#888;margin:6px 0 0;">対象{len(pitchers)}人 ｜ '
           f"単価中央値: 約{p_median:,.0f}万円/奪三振</p>" if pitchers else "")
    )
    faq = (
        '<h2 style="font-size:17px;margin:20px 0 6px;">このページの使い方</h2>'
        '<p style="font-size:13px;line-height:1.8;margin:0 0 8px;">'
        "シーズンが進むほど安打・奪三振が積み上がり単価は下がるため、<b>順位の変動</b>と"
        "<b>中央値比の推移</b>に意味があります。契約更改の時期には「今季の単価」が"
        "そのまま年俸査定の議論材料になります。選手名のリンク先（年俸推移ページ）で、"
        "その選手の年俸がどう積み上がってきたかと合わせて見るのがおすすめです。</p>"
        f'<p style="font-size:13px;margin:0 0 4px;">関連: <a href="{SALARY_URL}/">巨人 年俸一覧・選手別年俸推移</a>'
        f' ｜ <a href="{CLUSTER_URL}/">巨人選手データTOP</a></p>'
    )
    return (
        breadcrumb_jsonld("巨人 年俸コスパ分析", SLUG)
        + dataset_jsonld(
            name=f"巨人 年俸コスパ分析 {year} (1安打/1奪三振あたりの推定年俸)",
            description=render_salary_value_excerpt(data), slug=SLUG)
        + nav + lead + how + b_sec + p_sec + faq
    )
