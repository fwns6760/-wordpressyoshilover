"""
sports_fetcher.py — スポーツナビから巨人の試合データを取得してWP記事を自動生成

使用例:
    python3 src/sports_fetcher.py starters   # 今日のスタメン記事を公開
    python3 src/sports_fetcher.py result     # 試合結果記事を公開
    python3 src/sports_fetcher.py starters --dry-run
"""

import sys
import os
import re
import json
import argparse
import logging
import urllib.request
import urllib.parse
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

_vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'vendor')
if os.path.isdir(_vendor) and _vendor not in sys.path:
    sys.path.insert(0, _vendor)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from wp_client import WPClient

# ──────────────────────────────────────────────────────────
# ログ
# ──────────────────────────────────────────────────────────
LOG_FILE = ROOT / "logs" / "sports_fetcher.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

GIANTS_TEAM_ID = 1  # スポーツナビの読売巨人ID
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
HISTORY_FILE = ROOT / "data" / "sports_history.json"

# ──────────────────────────────────────────────────────────
# HTTP取得ヘルパー
# ──────────────────────────────────────────────────────────
def fetch_html(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as res:
            return res.read(200000).decode("utf-8", errors="ignore")
    except Exception as e:
        logger.error(f"取得失敗 {url}: {e}")
        return ""

# ──────────────────────────────────────────────────────────
# 今日の巨人の試合IDを取得
# ──────────────────────────────────────────────────────────
def get_today_game() -> dict:
    today = date.today().strftime("%Y%m%d")
    url = f"https://baseball.yahoo.co.jp/npb/teams/{GIANTS_TEAM_ID}/schedule/"
    html = fetch_html(url)
    if not html:
        return {}

    # 試合IDを探す（/npb/game/XXXXXXXXXX/score 形式）
    pattern = r'/npb/game/(\d+)/score'
    game_ids = re.findall(pattern, html)

    for game_id in game_ids:
        game_url = f"https://baseball.yahoo.co.jp/npb/game/{game_id}/score"
        game_html = fetch_html(game_url)
        if not game_html:
            continue
        if today[:8] in game_id[:8] or today in game_html[:5000]:
            # 対戦相手を取得
            opp_match = re.search(r'class="[^"]*bb-gameScoreTable__teamName[^"]*"[^>]*>([^<]+)<', game_html)
            opponent = opp_match.group(1).strip() if opp_match else "対戦相手"
            return {
                "game_id": game_id,
                "game_url": game_url,
                "opponent": opponent,
                "date": today,
            }

    # 直接URLパターンで今日の試合を探す
    year = today[:4]
    url2 = f"https://baseball.yahoo.co.jp/npb/schedule/?year={year}&month={today[4:6]}"
    html2 = fetch_html(url2)
    ids2 = re.findall(r'/npb/game/(\d+)', html2)
    for gid in set(ids2):
        if gid.startswith(year):
            return {"game_id": gid, "game_url": f"https://baseball.yahoo.co.jp/npb/game/{gid}/score",
                    "opponent": "対戦相手", "date": today}

    return {}

# ──────────────────────────────────────────────────────────
# スタメン・打率取得
# ──────────────────────────────────────────────────────────
def get_starters(game_id: str) -> dict:
    url = f"https://baseball.yahoo.co.jp/npb/game/{game_id}/top"
    html = fetch_html(url)
    if not html:
        return {"giants": [], "opponent": [], "opponent_name": "対戦相手"}

    result = {"giants": [], "opponent": [], "opponent_name": "対戦相手"}

    # bb-splitsTable から行を抽出
    # <td class="bb-splitsTable__data">1</td>  打順
    # <td class="bb-splitsTable__data">二</td>  守備
    # <td ...--text"><a ...>門脇 誠</a></td>   選手名
    # <td ...>左</td>                           打席
    # <td ...--score">.200</td>                 打率
    row_pattern = (
        r'<td[^>]*bb-splitsTable__data[^>]*>(\d)</td>\s*'
        r'<td[^>]*bb-splitsTable__data[^>]*>([^<]+)</td>\s*'
        r'<td[^>]*bb-splitsTable__data[^>]*>.*?<a[^>]*>([^<]+)</a>.*?</td>\s*'
        r'<td[^>]*bb-splitsTable__data[^>]*>[^<]*</td>\s*'
        r'<td[^>]*bb-splitsTable__data--score[^>]*>([^<]+)</td>'
    )
    all_players = re.findall(row_pattern, html, re.DOTALL)

    def parse_lineup(section: str) -> list:
        hits = re.findall(row_pattern, section, re.DOTALL)
        lineup = []
        seen = set()
        for order, pos, name, avg in hits:
            key = name.strip()
            if key in seen:
                continue
            seen.add(key)
            lineup.append({
                "order":    order.strip(),
                "position": pos.strip(),
                "name":     name.strip(),
                "avg":      avg.strip(),
            })
            if int(order.strip()) == 9:
                break
        return lineup[:9]

    # npbTeam1（巨人）とnpbTeam2（対戦相手）でHTML分割
    team1_match = re.search(r'bb-splitsTable--npbTeam1', html)
    team2_match = re.search(r'bb-splitsTable--npbTeam2', html)

    if team1_match and team2_match:
        pos1 = team1_match.start()
        pos2 = team2_match.start()
        if pos1 < pos2:
            html_team1 = html[pos1:pos2]
            html_team2 = html[pos2:]
        else:
            html_team1 = html[pos1:]
            html_team2 = html[pos2:pos1]
    else:
        mid = len(html) // 2
        html_team1 = html[:mid]
        html_team2 = html[mid:]

    lineup1 = parse_lineup(html_team1)
    lineup2 = parse_lineup(html_team2)

    # 対戦相手チーム名取得
    opp_name_match = re.search(r'bb-splitsTable--npbTeam2.*?<th[^>]*>([^<]+)</th>', html, re.DOTALL)
    if not opp_name_match:
        opp_name_match = re.search(r'npbTeam2[^>]*>[^<]*<[^>]*>([^\s<]+)', html)
    if opp_name_match:
        result["opponent_name"] = opp_name_match.group(1).strip()

    # 9人以上取れた方を巨人と判定（または選手名で判断）
    giants_keywords = ["門脇", "泉口", "中山", "ダルベック", "キャベッジ", "坂本", "岡本", "丸", "吉川", "大城", "山瀬", "戸郷", "菅野", "井上", "大勢", "モンテス", "浦田", "松本", "平山"]
    def is_giants(lineup: list) -> bool:
        names = " ".join(p["name"] for p in lineup)
        return any(k in names for k in giants_keywords)

    if is_giants(lineup1):
        result["giants"]   = lineup1
        result["opponent"] = lineup2
    else:
        result["giants"]   = lineup2
        result["opponent"] = lineup1

    # 対戦相手チーム名
    opp_match = re.search(r'(?:vs|VS|対)\s*([^\s<\"]+)', html[:3000])
    if opp_match:
        result["opponent_name"] = opp_match.group(1)

    return result

# ──────────────────────────────────────────────────────────
# 試合結果取得
# ──────────────────────────────────────────────────────────
def get_game_result(game_id: str) -> dict:
    url = f"https://baseball.yahoo.co.jp/npb/game/{game_id}/score"
    html = fetch_html(url)
    if not html:
        return {}

    result = {}

    # イニングスコア
    score_match = re.search(r'bb-gameInningScore.*?(<table.*?</table>)', html, re.DOTALL)
    if score_match:
        score_html = score_match.group(1)
        result["score_html"] = score_html

    # 最終スコア
    total_match = re.findall(r'bb-gameScoreTable__total[^>]*>(\d+)<', html)
    if len(total_match) >= 2:
        result["giants_score"]  = total_match[0]
        result["opponent_score"] = total_match[1]

    return result

# ──────────────────────────────────────────────────────────
# スタメン記事HTML生成（のもとけ風）
# ──────────────────────────────────────────────────────────
def build_starters_html(starters: dict, game_info: dict) -> str:
    today_str = datetime.now().strftime("%Y年%-m月%-d日")
    opponent  = game_info.get("opponent", "対戦相手")

    def lineup_table(players: list, team: str) -> str:
        if not players:
            return f"<p>（{team}スタメン取得中）</p>"
        rows = ""
        for p in players:
            rows += (
                f'<tr>'
                f'<td style="text-align:center;width:30px;font-weight:700;">{p["order"]}</td>'
                f'<td style="text-align:center;width:40px;color:#666;">（{p["position"]}）</td>'
                f'<td style="font-weight:700;">{p["name"]}</td>'
                f'<td style="text-align:right;color:#F5811F;font-weight:700;">{p["avg"]}</td>'
                f'</tr>'
            )
        return (
            f'<table style="width:100%;border-collapse:collapse;font-size:14px;">'
            f'<thead><tr style="background:#1A1A1A;color:#fff;">'
            f'<th colspan="4" style="padding:8px 12px;text-align:left;">{team} スタメン / 打率</th>'
            f'</tr></thead>'
            f'<tbody>{rows}</tbody>'
            f'</table>'
        )

    giants_table  = lineup_table(starters.get("giants", []),   "【巨人】")
    opponent_table = lineup_table(starters.get("opponent", []), f"【{opponent}】")

    return f"""<!-- wp:html -->
<div style="background:#fff;border:1px solid #e8e8e8;border-top:3px solid #F5811F;padding:16px;border-radius:4px;margin-bottom:16px;">
  <p style="font-size:13px;color:#666;margin-bottom:12px;">{today_str} のスタメン発表です。</p>
  {giants_table}
  <div style="margin-top:12px;"></div>
  {opponent_table}
</div>
<!-- /wp:html -->

<!-- wp:paragraph -->
<p>みなさんの予想・期待をコメントで教えてください！</p>
<!-- /wp:paragraph -->"""

# ──────────────────────────────────────────────────────────
# 試合結果記事HTML生成
# ──────────────────────────────────────────────────────────
def build_result_html(result: dict, starters: dict, game_info: dict) -> str:
    opponent = game_info.get("opponent", "対戦相手")
    g_score  = result.get("giants_score", "-")
    o_score  = result.get("opponent_score", "-")
    today_str = datetime.now().strftime("%Y年%-m月%-d日")

    try:
        win = int(g_score) > int(o_score)
        result_label = "勝利" if win else "敗戦"
        result_color = "#F5811F" if win else "#666"
    except Exception:
        result_label = "試合終了"
        result_color = "#666"

    return f"""<!-- wp:html -->
<div style="background:#fff;border:1px solid #e8e8e8;border-top:3px solid {result_color};padding:16px;border-radius:4px;margin-bottom:16px;">
  <p style="font-size:13px;color:#666;margin-bottom:8px;">{today_str} 試合結果</p>
  <div style="text-align:center;padding:16px 0;">
    <span style="font-size:32px;font-weight:700;color:#1A1A1A;">巨人 {g_score}</span>
    <span style="font-size:18px;color:#999;margin:0 12px;">-</span>
    <span style="font-size:32px;font-weight:700;color:#1A1A1A;">{o_score} {opponent}</span>
  </div>
  <div style="text-align:center;">
    <span style="background:{result_color};color:#fff;padding:4px 20px;border-radius:20px;font-weight:700;font-size:16px;">{result_label}</span>
  </div>
</div>
<!-- /wp:html -->

<!-- wp:paragraph -->
<p>試合の感想・コメントをお願いします！</p>
<!-- /wp:paragraph -->"""

# ──────────────────────────────────────────────────────────
# 履歴管理（同じ試合を重複投稿しない）
# ──────────────────────────────────────────────────────────
def load_history() -> dict:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(key: str, history: dict):
    history[key] = datetime.now().isoformat()
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# ──────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="スポーツナビから試合データを取得してWP記事を公開")
    parser.add_argument("command", choices=["starters", "result"], help="starters: スタメン記事 / result: 試合結果記事")
    parser.add_argument("--dry-run", action="store_true", help="実際には投稿しない")
    parser.add_argument("--game-id", help="試合IDを直接指定")
    args = parser.parse_args()

    logger.info(f"=== sports_fetcher {args.command} 開始 {'[DRY RUN]' if args.dry_run else ''} ===")

    # 今日の試合を取得
    if args.game_id:
        game_info = {"game_id": args.game_id, "game_url": f"https://baseball.yahoo.co.jp/npb/game/{args.game_id}/score", "opponent": "対戦相手", "date": date.today().strftime("%Y%m%d")}
    else:
        game_info = get_today_game()

    if not game_info:
        logger.info("今日の試合が見つかりませんでした（試合なし or スケジュール取得失敗）")
        return

    game_id  = game_info["game_id"]
    opponent = game_info.get("opponent", "対戦相手")
    today    = date.today().strftime("%Y%m%d")
    logger.info(f"試合ID: {game_id} / 対戦相手: {opponent}")

    history = load_history()
    history_key = f"{args.command}_{today}"

    if history_key in history and not args.dry_run:
        logger.info(f"本日分はすでに投稿済みです（{history[history_key]}）")
        return

    starters = get_starters(game_id)
    logger.info(f"スタメン取得: 巨人{len(starters.get('giants', []))}名 / {opponent}{len(starters.get('opponent', []))}名")

    if args.command == "starters":
        today_str = datetime.now().strftime("%-m月%-d日")
        title   = f"【巨人スタメン発表】{today_str} 巨人vs{opponent} 本日のスタメン・打率"
        content = build_starters_html(starters, game_info)
        category = "試合速報"

    elif args.command == "result":
        result_data = get_game_result(game_id)
        g_score = result_data.get("giants_score", "-")
        o_score = result_data.get("opponent_score", "-")
        today_str = datetime.now().strftime("%-m月%-d日")
        try:
            win = int(g_score) > int(o_score)
            label = "勝利" if win else "敗戦"
        except Exception:
            label = "試合終了"
        title   = f"【巨人{label}】{today_str} 巨人{g_score}-{o_score}{opponent} 試合結果"
        content = build_result_html(result_data, starters, game_info)
        category = "試合速報"

    if args.dry_run:
        print(f"\nタイトル: {title}")
        print(f"カテゴリ: {category}")
        print("本文（HTML）:")
        print(content[:500])
        return

    wp = WPClient()
    category_id = wp.resolve_category_id(category)
    post_id = wp.create_post(
        title,
        content,
        categories=[category_id] if category_id else None,
        status="publish",
        allow_status_upgrade=True,
        caller="sports_fetcher.main",
        source_lane="sports_fetcher",
    )
    logger.info(f"公開完了 post_id={post_id}")
    save_history(history_key, history)

    # X投稿
    try:
        import subprocess
        script = str(ROOT / "src" / "x_api_client.py")
        subprocess.run([sys.executable, script, "post", "--post-id", str(post_id)], timeout=30)
    except Exception as e:
        logger.warning(f"X投稿失敗（スキップ）: {e}")

if __name__ == "__main__":
    main()
