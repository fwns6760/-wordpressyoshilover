"""one-shot: 吉川尚輝の復帰後 全成績(打撃・走塁・守備)記事を publish."""
import os
import sys
from datetime import datetime

sys.path.insert(0, "src")
import requests

from wp_client import WPClient

# データ source:
#  - 打撃 / 走塁: NPB 公式 (https://npb.jp/bis/players/73375134.html)
#  - 守備: プロ野球ヌルデータ置き場 (https://nf3.sakura.ne.jp/Central/G/f/2_stat.htm)
PERIOD_START = "2026-04-26"
PERIOD_END = "2026-05-14"
PLAYER = "吉川尚輝"
EYECATCH_MEDIA_ID = 66859
CATEGORY_ID = 675  # データで見る巨人

# 計算
SLG = 0.205  # 長打率
OBP = 0.255  # 出塁率
OPS = round(OBP + SLG, 3)


def build_html() -> str:
    parts = []
    parts.append(
        '<p>巨人の吉川尚輝が 4 月 26 日に 1 軍復帰してからの全成績を、'
        '打撃・走塁・守備の 3 area で表にまとめました。'
        '前年 10 月の両股関節手術を経ての復帰、約 6 ヶ月ぶりの 1 軍出場でした。</p>'
    )

    parts.append('<h3>復帰後の成績(打撃)</h3>')
    parts.append('<table>')
    parts.append('<thead><tr><th>項目</th><th>数値</th></tr></thead>')
    parts.append('<tbody>')
    batting_rows = [
        ("試合", "14"),
        ("打席", "47"),
        ("打数", "44"),
        ("安打", "9"),
        ("二塁打", "0"),
        ("三塁打", "0"),
        ("本塁打", "0"),
        ("打点", "1"),
        ("得点", "4"),
        ("四球", "3"),
        ("死球", "0"),
        ("三振", "6"),
        ("犠打", "0"),
        ("犠飛", "0"),
        ("打率", ".205"),
        ("出塁率", ".255"),
        ("長打率", ".205"),
        ("OPS", f".{int(OPS*1000):03d}"),
    ]
    for k, v in batting_rows:
        parts.append(f'<tr><td>{k}</td><td><strong>{v}</strong></td></tr>')
    parts.append('</tbody></table>')

    parts.append('<h3>復帰後の成績(走塁)</h3>')
    parts.append('<table>')
    parts.append('<thead><tr><th>項目</th><th>数値</th></tr></thead>')
    parts.append('<tbody>')
    run_rows = [
        ("盗塁", "<strong>2</strong>"),
        ("盗塁刺", "0"),
        ("盗塁成功率", "<strong>100%</strong>"),
    ]
    for k, v in run_rows:
        parts.append(f'<tr><td>{k}</td><td>{v}</td></tr>')
    parts.append('</tbody></table>')

    parts.append('<h3>復帰後の成績(守備)</h3>')
    parts.append('<table>')
    parts.append('<thead><tr><th>項目</th><th>数値</th></tr></thead>')
    parts.append('<tbody>')
    field_rows = [
        ("守備位置", "二塁手(主)"),
        ("二塁手 先発", "11 試合"),
        ("二塁手 途中出場", "3 試合"),
        ("失策", '<span style="color:#c0392b"><strong>0</strong></span>'),
        ("守備率", '<span style="color:#c0392b"><strong>1.000</strong></span>'),
        ("刺殺 / 補殺 / 併殺", "規定到達後の NPB 公式に掲載予定"),
    ]
    for k, v in field_rows:
        parts.append(f'<tr><td>{k}</td><td>{v}</td></tr>')
    parts.append('</tbody></table>')

    parts.append('<h3>ひとことで言うと</h3>')
    parts.append(
        '<p><strong>守備で失策ゼロ、走塁で盗塁 2 / 成功率 100%</strong>。'
        '打撃面はまだ手術明けの調整段階(打率 .205 / OPS .460)ですが、'
        '失策ゼロは復帰直後としては安心材料です。'
        '今後の打撃の戻りに注目です。</p>'
    )

    parts.append('<h3>このデータについて</h3>')
    parts.append('<table>')
    parts.append('<thead><tr><th>項目</th><th>内容</th></tr></thead>')
    parts.append('<tbody>')
    meta_rows = [
        ("選手", "<strong>吉川尚輝</strong>(読売ジャイアンツ)"),
        ("集計期間", f"{PERIOD_START} 〜 {PERIOD_END}(1 軍復帰後の全試合)"),
        ("試合数", "14 試合"),
        ("打撃データ元", '<a href="https://npb.jp/bis/players/73375134.html">NPB 公式 個人年度別成績</a>'),
        ("守備データ元", '<a href="https://nf3.sakura.ne.jp/Central/G/f/2_stat.htm">プロ野球ヌルデータ置き場(セリーグ巨人 守備)</a>'),
        ("背景", "前年 10 月に両股関節の手術、約 6 ヶ月ぶりの 1 軍復帰"),
    ]
    for k, v in meta_rows:
        parts.append(f'<tr><td>{k}</td><td>{v}</td></tr>')
    parts.append('</tbody></table>')

    return "\n".join(parts)


def main():
    title = "【巨人データを見る】吉川尚輝、復帰後の打撃・走塁・守備 全成績(4/26〜5/14)"
    body = build_html()

    wp = WPClient()
    auth = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])

    # tag 確保
    tag_id = 0
    try:
        r = requests.get(
            f"{wp.base_url}/wp-json/wp/v2/tags?search=吉川尚輝&per_page=10",
            auth=auth, timeout=15,
        )
        for t in r.json():
            if t.get("name") == "吉川尚輝":
                tag_id = int(t["id"]); break
        if not tag_id:
            r = requests.post(
                f"{wp.base_url}/wp-json/wp/v2/tags",
                auth=auth, json={"name": "吉川尚輝"}, timeout=15,
            )
            tag_id = int(r.json().get("id") or 0)
    except Exception as e:
        print(f"tag warn: {e}")

    payload = {
        "title": title,
        "content": body,
        "status": "publish",
        "categories": [CATEGORY_ID],
        "featured_media": EYECATCH_MEDIA_ID,
    }
    if tag_id:
        payload["tags"] = [tag_id]

    r = requests.post(
        f"{wp.base_url}/wp-json/wp/v2/posts",
        auth=auth, json=payload, timeout=30,
    )
    if r.status_code in (200, 201):
        pid = r.json().get("id")
        link = r.json().get("link")
        print(f"published: id={pid} link={link}")
    else:
        print(f"FAIL {r.status_code}: {r.text[:300]}")


if __name__ == "__main__":
    main()
