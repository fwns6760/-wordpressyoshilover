"""
create_test_posts.py — テスト記事10本作成スクリプト
=====================================================
読売ジャイアンツ関連のダミーニュース記事を8カテゴリに振り分けて10本作成する。
記事1本にXポスト埋め込みブロックを含む（Xカード表示の動作確認用）。

使用方法:
    python3 src/create_test_posts.py            # 公開状態で作成
    python3 src/create_test_posts.py --draft    # 下書きで作成
    python3 src/create_test_posts.py --dry-run  # 確認のみ（変更なし）
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

JST = timezone(timedelta(hours=9))

# ──────────────────────────────────────────────────────────────────
# Gutenberg ブロックヘルパー
# ──────────────────────────────────────────────────────────────────

def paragraph(text: str) -> str:
    return f"<!-- wp:paragraph -->\n<p>{text}</p>\n<!-- /wp:paragraph -->"

def heading2(text: str) -> str:
    return f'<!-- wp:heading {{"level":2}} -->\n<h2>{text}</h2>\n<!-- /wp:heading -->'

def heading3(text: str) -> str:
    return f'<!-- wp:heading {{"level":3}} -->\n<h3>{text}</h3>\n<!-- /wp:heading -->'

def separator() -> str:
    return "<!-- wp:separator -->\n<hr class=\"wp-block-separator has-alpha-channel-opacity\"/>\n<!-- /wp:separator -->"

def x_embed(url: str) -> str:
    """X(Twitter)のポストをGutenbergのembedブロックとして返す"""
    return (
        f'<!-- wp:embed {{"url":"{url}","type":"rich",'
        f'"providerNameSlug":"twitter","responsive":true,'
        f'"className":"wp-embed-aspect-1-1 wp-has-aspect-ratio"}} -->\n'
        f'<figure class="wp-block-embed is-type-rich is-provider-twitter '
        f'wp-block-embed-twitter wp-embed-aspect-1-1 wp-has-aspect-ratio">\n'
        f'<div class="wp-block-embed__wrapper">\n'
        f'{url}\n'
        f'</div></figure>\n'
        f'<!-- /wp:embed -->'
    )

def quote(text: str, cite: str = "") -> str:
    cite_attr = f' cite="{cite}"' if cite else ""
    cite_tag = f'<cite>{cite}</cite>' if cite else ""
    return (
        f'<!-- wp:quote -->\n'
        f'<blockquote class="wp-block-quote"{cite_attr}>'
        f'<p>{text}</p>{cite_tag}'
        f'</blockquote>\n'
        f'<!-- /wp:quote -->'
    )

def blocks(*parts: str) -> str:
    return "\n\n".join(parts)


# ──────────────────────────────────────────────────────────────────
# 記事データ（巨人関連ダミーニュース）
# ──────────────────────────────────────────────────────────────────
# X埋め込みURL: @yomiuri_giants（読売ジャイアンツ公式）の実在ポストを使用。
# ※ 以下のURLは動作確認用のプレースホルダーです。
#   実際の確認時は WP管理画面で記事を開き、Xカードが表示されることを確認してください。
#   表示されない場合は https://x.com/yomiuri_giants の直近ポストURLに差し替えてください。
X_TEST_URL = "https://x.com/yomiuri_giants/status/1899999999999999999"

ARTICLES = [
    # ① 試合速報（Xポスト埋め込みあり）
    {
        "category": "試合速報",
        "title": "【試合速報】巨人3-2阪神｜岡本和真の逆転3ランで劇的勝利！戸郷翔征が7回1失点好投",
        "content": blocks(
            paragraph(
                "4月12日（土）、東京ドームで行われた読売ジャイアンツvs阪神タイガースの一戦は、"
                "岡本和真の7回逆転3ランホームランが決勝点となり、巨人が3対2で勝利した。"
            ),
            heading2("試合ハイライト"),
            paragraph(
                "先発の戸郷翔征は7回を投げ1失点の好投。"
                "打線は6回まで阪神の先発・伊藤将司に抑えられていたが、"
                "7回表に岡本和真が打席に入り、2ストライクから低めのカットボールを完璧に捉えた。"
                "打球は左中間スタンドへ飛び込む逆転3ランとなり、東京ドームが沸いた。"
            ),
            heading3("岡本和真のコメント"),
            quote(
                "追い込まれてからも自分のスイングができた。チームが苦しいところで打てて本当に良かった。",
                "岡本和真（試合後インタビュー）"
            ),
            separator(),
            heading2("公式Xポスト"),
            paragraph("読売ジャイアンツ公式がX（旧Twitter）でこの試合を速報。"),
            x_embed(X_TEST_URL),
            separator(),
            heading2("スコアボード"),
            paragraph(
                "阪神　0 0 1 0 1 0 0 0 0 ｜ 2<br>"
                "巨人　0 0 0 0 0 0 3 0 × ｜ 3<br><br>"
                "【本塁打】岡本和真7号（7回逆転3ラン）<br>"
                "【勝利投手】戸郷翔征（3勝0敗）"
            ),
        ),
    },

    # ② 試合速報
    {
        "category": "試合速報",
        "title": "【試合速報】巨人7-0ヤクルト｜山崎伊織が今季初完封！坂本勇人3打数2安打の活躍",
        "content": blocks(
            paragraph(
                "4月10日（木）、東京ドームで行われた巨人vsヤクルト戦は、"
                "山崎伊織が9回を完封する圧巻の投球で、巨人が7対0で快勝した。"
            ),
            heading2("山崎伊織、今季初完封"),
            paragraph(
                "山崎は変化球のキレが抜群で、ヤクルト打線を7奪三振・無四球に封じた。"
                "「今日は全球種が決まった。完封は狙っていなかったが、9回も任せてもらえてうれしかった」とコメント。"
            ),
            heading2("坂本勇人が存在感"),
            paragraph(
                "坂本勇人は3番に入り、3打数2安打2打点の活躍。"
                "「まだまだやれる」と強調し、チームを牽引した。"
                "4回の2点タイムリーは、外角低めのスライダーを逆方向に流し打ちする技あり打席だった。"
            ),
        ),
    },

    # ③ 選手情報（Xポスト埋め込みなし）
    {
        "category": "選手情報",
        "title": "岡本和真インタビュー「今年は50本狙う」オープン戦絶好調で本番へ準備万端",
        "content": blocks(
            paragraph(
                "オープン戦で打率.389・5本塁打と絶好調の岡本和真が、開幕前インタビューに応じた。"
                "今季の目標として「50本塁打・打率.310・100打点」を掲げ、"
                "「3冠王を意識して打席に入りたい」と力強く語った。"
            ),
            heading2("フォーム改造の成果"),
            paragraph(
                "今オフはスイング軌道を見直し、バットの出どころを改善した。"
                "コーチ陣との徹底した映像分析の結果、右肩の開きを抑えることに成功。"
                "これにより外角の変化球に対応できるようになったという。"
            ),
            heading2("チームへの期待"),
            paragraph(
                "「今年はチームも勝てる戦力が揃っている。自分がチームの中心として引っ張って、"
                "日本一を取りたい」と岡本は宣言。4番として背負う重圧を楽しんでいる様子が印象的だった。"
            ),
            quote(
                "今年こそ50本。チームが勝てば個人成績はついてくると信じてやるだけです。",
                "岡本和真"
            ),
        ),
    },

    # ④ 選手情報
    {
        "category": "選手情報",
        "title": "戸郷翔征2026年シーズン展望｜開幕エース確定、球速UP＆新変化球で三振量産狙う",
        "content": blocks(
            paragraph(
                "今季の巨人エースとして期待される戸郷翔征（25）が、春季キャンプでの手応えを語った。"
                "オフに取り組んだ体幹トレーニングの成果で最速が2km/h上昇し、"
                "152km/hをマークする場面も見られた。"
            ),
            heading2("新球種「スプリット改」を投入"),
            paragraph(
                "今季の目玉は新たに磨いたスプリットボールの精度向上。"
                "従来のフォークボールより沈む変化を実現し、「三振を取れる決め球が一つ増えた」と自信を見せた。"
                "打者のタイミングを外す「遅いスプリット」と速い直球との組み合わせが機能すれば、"
                "奪三振率がさらに上昇する可能性がある。"
            ),
            heading2("目標は15勝＆防御率2.00以下"),
            quote(
                "去年の反省を活かして、シーズン通じて先発ローテを守りたい。防御率2点台は絶対キープする。",
                "戸郷翔征"
            ),
        ),
    },

    # ⑤ 首脳陣
    {
        "category": "首脳陣",
        "title": "阿部慎之助監督会見「若手を積極的に使う。失敗を恐れない野球を目指す」春季キャンプ総括",
        "content": blocks(
            paragraph(
                "読売ジャイアンツの阿部慎之助監督が、春季キャンプを総括する会見を行った。"
                "今季の方針として「若手育成と勝利の両立」を掲げ、"
                "経験よりもポテンシャルを重視した起用を続けていく姿勢を示した。"
            ),
            heading2("若手野手の起用方針"),
            paragraph(
                "「若い選手は失敗して当然。でもその失敗から学べる環境を作るのが私の仕事。"
                "今年は思い切って若手を使う。それがチームの長期的な強化につながる」と語った。"
                "特にドラフト2位で入団した新人外野手の積極起用を示唆した発言が注目を集めた。"
            ),
            heading2("投手起用の考え方"),
            paragraph(
                "先発ローテは戸郷翔征を軸に構築し、若手の山崎伊織が2番手として期待されている。"
                "「勝ちパターンのリリーフを固めることで先発への負担を減らしたい」とも語った。"
            ),
            quote(
                "選手が気持ちよく戦える環境を作るのが私の役目。今年は日本一以外は考えていない。",
                "阿部慎之助監督"
            ),
        ),
    },

    # ⑥ ドラフト・育成
    {
        "category": "ドラフト・育成",
        "title": "【ファーム速報】ドラフト1位・森田大翔が一軍昇格へ急接近！153km/hをマーク、首脳陣が高評価",
        "content": blocks(
            paragraph(
                "巨人ドラフト1位ルーキーの森田大翔投手（22）が、"
                "二軍戦で3試合連続好投を続けており、一軍昇格が現実味を帯びてきた。"
                "直近の登板では自己最速となる153km/hをマークし、球団関係者から高い評価を受けている。"
            ),
            heading2("スカウトが語る潜在能力"),
            paragraph(
                "「あれだけボールに力があって制球も安定している投手はなかなかいない。"
                "変化球の精度が上がれば今すぐ一軍で通用する」とスカウト部長がコメント。"
            ),
            heading2("本人のコメント"),
            quote(
                "一軍では使ってもらえるかどうかじゃなく、"
                "二軍で結果を積み上げることだけを考えています。",
                "森田大翔"
            ),
            heading2("育成システムの充実"),
            paragraph(
                "巨人は近年、育成選手の育成体制を大幅に強化。"
                "専任コーチの増員と最新テクノロジーを活用したデータ分析により、"
                "育成選手の一軍昇格率が向上している。"
            ),
        ),
    },

    # ⑦ OB・解説者
    {
        "category": "OB・解説者",
        "title": "高橋由伸氏が徹底分析「岡本はMVP候補筆頭。長打＋打率の両立は松井以来」今季の巨人展望",
        "content": blocks(
            paragraph(
                "元巨人4番打者で現在野球解説者を務める高橋由伸氏が、"
                "スポーツ番組で今季の巨人と岡本和真について詳しく分析した。"
            ),
            heading2("岡本への高評価"),
            quote(
                "あれだけパワーと技術を兼ね備えた打者は、巨人では松井秀喜以来じゃないか。"
                "長打力と打率の両立ができる選手で、今年はMVPを取ってもおかしくない数字を出してくれると期待している。",
                "高橋由伸氏（スポーツ解説番組）"
            ),
            heading2("チーム全体の評価"),
            paragraph(
                "「投手陣は戸郷・山崎の二枚看板が機能すれば安定する。"
                "問題は打線全体の底上げ。若手が成長してくれれば、リーグ連覇も十分狙える」と語った。"
                "また「阿部監督の采配はデータ活用と勘のバランスが取れている」とも評価した。"
            ),
        ),
    },

    # ⑧ 補強・移籍
    {
        "category": "補強・移籍",
        "title": "巨人が国内FA選手の獲得に動く？外野手補強の最有力候補として複数名との接触報道",
        "content": blocks(
            paragraph(
                "今オフのFA市場で巨人が外野手の補強に動く可能性があると、複数のスポーツ紙が報じている。"
                "外野の層を厚くすることが今季の課題とされており、"
                "球団フロントが積極的な補強姿勢を示しているという。"
            ),
            heading2("補強の背景"),
            paragraph(
                "昨シーズン、外野守備でのミスが勝敗に影響した場面が複数あったことから、"
                "「守れて打てる」外野手の補強が急務とされている。"
                "球団関係者は「戦力補強は常に考えている。良い選手がいれば積極的に動く」と語るにとどめた。"
            ),
            heading2("複数のFA選手が候補に"),
            paragraph(
                "今オフにFA権を取得する選手の中には、打率や守備力で実績のある選手が複数おり、"
                "巨人のスカウト陣が昨シーズンから追跡していたとされる。"
                "詳細は今後の情報を待ちたい。"
            ),
            quote(
                "戦力の上積みはシーズン通じての課題。オフは積極的な補強を検討する。",
                "球団フロント関係者（匿名）"
            ),
        ),
    },

    # ⑨ 球団情報
    {
        "category": "球団情報",
        "title": "東京ドーム2026シーズン限定グルメ＆応援グッズ発表！岡本モデルの限定ユニフォームが人気",
        "content": blocks(
            paragraph(
                "読売ジャイアンツは2026年シーズンの東京ドーム向け限定グルメと公式グッズの新ラインナップを発表した。"
                "特に岡本和真モデルの限定ユニフォームは予約開始から数時間で完売し、"
                "ファンの間で話題となっている。"
            ),
            heading2("2026年限定グルメ"),
            paragraph(
                "今季の目玉グルメは「岡本和真のビッグカツバーガー」（1,200円）と"
                "「戸郷翔征のエース丼」（950円）の2種。"
                "いずれも試合前から長蛇の列ができるほどの人気ぶりだという。"
                "また、球場限定クラフトビール「GIANTS ORANGE ALE」（800円）も登場した。"
            ),
            heading2("応援グッズの新デザイン"),
            paragraph(
                "2026年のメガホンは恒例のオレンジに加え、「ジャイアンツブルー」カラーの新作も登場。"
                "ユニフォームはホーム・ビジター各モデルで素材がリニューアルされ、"
                "着心地と通気性が向上した。限定ユニフォームの再販は未定とのこと。"
            ),
        ),
    },

    # ⑩ コラム
    {
        "category": "コラム",
        "title": "【コラム】2026年セ・リーグ優勝予想｜データで見る巨人連覇の可能性と阻む壁",
        "content": blocks(
            paragraph(
                "昨シーズンのリーグ優勝から2年連続Vを目指す読売ジャイアンツ。"
                "今季のチーム力を投打のデータから分析し、連覇の可能性を探る。"
            ),
            heading2("投手力は12球団トップクラス"),
            paragraph(
                "先発・戸郷翔征、山崎伊織、リリーフ陣の安定感は依然として高く、"
                "チーム防御率は昨季比で0.15改善が見込まれる。"
                "特に「ホールド+セーブ率」は12球団平均を15%上回っており、"
                "接戦での強さが際立つ。"
            ),
            heading2("打線の課題と可能性"),
            paragraph(
                "岡本を軸とした打線は潜在能力が高い一方、中軸以降の得点圏打率が課題。"
                "昨季の得点圏打率.268をいかに上積みするかがリーグ優勝への鍵となる。"
                "若手外野手の台頭があれば、打線に厚みが生まれ優勝確率は大幅に上昇する。"
            ),
            heading2("予想優勝確率"),
            paragraph(
                "各指標を総合すると、巨人の優勝確率は約38%と推定される（筆者試算）。"
                "2位候補のDeNAが32%、阪神が19%と続く。"
                "投手力の安定を考えれば優勝争いの中心にいることは間違いなく、"
                "岡本・戸郷の二枚看板がフル稼働できれば他球団を圧倒する可能性は十分にある。"
            ),
            quote(
                "今年の巨人は強い。ただし先発3番手の安定が連覇の分岐点になる。",
                "筆者"
            ),
        ),
    },
]


# ──────────────────────────────────────────────────────────────────
# 投稿クライアント
# ──────────────────────────────────────────────────────────────────

class TestPostCreator:
    def __init__(self, dry_run: bool = False, status: str = "publish"):
        self.base_url     = os.getenv("WP_URL", "").rstrip("/")
        self.user         = os.getenv("WP_USER", "")
        self.app_password = os.getenv("WP_APP_PASSWORD", "")
        self.dry_run      = dry_run
        self.status       = status

        if not all([self.base_url, self.user, self.app_password]):
            raise ValueError(".env に WP_URL / WP_USER / WP_APP_PASSWORD が設定されていません")

        self.auth    = (self.user, self.app_password)
        self.api     = f"{self.base_url}/wp-json/wp/v2"
        self.headers = {"Content-Type": "application/json"}

        if dry_run:
            print("[DRY-RUN] 変更は行いません\n")

    def _check(self, resp: requests.Response, action: str):
        if resp.status_code == 401:
            raise PermissionError(f"認証失敗（{action}）")
        if resp.status_code == 403:
            raise PermissionError(f"アクセス拒否（{action}）")
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"HTTPエラー（{action}）: {e}\n{resp.text[:300]}")

    def _get_category_map(self) -> dict:
        """カテゴリ名 → WP ID のマップを返す"""
        # config/categories.json があれば使う
        cats_file = ROOT / "config" / "categories.json"
        if cats_file.exists():
            with open(cats_file, encoding="utf-8") as f:
                data = json.load(f)
            if data:
                return {k: v for k, v in data.items() if v}

        # なければ REST API から取得
        resp = requests.get(
            f"{self.api}/categories",
            params={"per_page": 100},
            auth=self.auth,
            timeout=30,
        )
        self._check(resp, "カテゴリ取得")
        return {c["name"]: c["id"] for c in resp.json()}

    def _check_existing_titles(self) -> set:
        """既存投稿タイトルの集合を返す（重複作成防止）"""
        resp = requests.get(
            f"{self.api}/posts",
            params={"per_page": 100, "status": "any"},
            auth=self.auth,
            timeout=30,
        )
        if not resp.ok:
            return set()
        return {p["title"]["rendered"] for p in resp.json()}

    def create_posts(self):
        print("=" * 55)
        print("テスト記事10本を作成")
        print("=" * 55)
        print(f"  ステータス: {self.status}")

        cat_map = self._get_category_map()
        print(f"  カテゴリ取得: {len(cat_map)}件")
        for name, wid in cat_map.items():
            print(f"    ID={wid:3d}  {name}")
        print()

        existing_titles = self._check_existing_titles()

        created, skipped, failed = 0, 0, 0

        # 投稿日時を少しずつずらして「活発な更新」を演出
        base_dt = datetime(2026, 4, 12, 10, 0, 0, tzinfo=JST)

        for i, article in enumerate(ARTICLES):
            title    = article["title"]
            cat_name = article["category"]
            content  = article["content"]

            if title in existing_titles:
                print(f"  [{i+1:02d}] スキップ（既存） {title[:40]}...")
                skipped += 1
                continue

            cat_id = cat_map.get(cat_name)
            if not cat_id:
                print(f"  [{i+1:02d}] ⚠️  カテゴリ未解決 「{cat_name}」 — setup_phase1.py を先に実行してください")
                failed += 1
                continue

            # 投稿日時：1本あたり30〜90分ずらす
            offset_minutes = i * 47 + (i % 3) * 23
            post_dt = base_dt - timedelta(minutes=offset_minutes)
            post_date = post_dt.strftime("%Y-%m-%dT%H:%M:%S")

            payload = {
                "title":      title,
                "content":    content,
                "status":     self.status,
                "categories": [cat_id],
                "date":       post_date,
                "comment_status": "open",
            }

            if self.dry_run:
                print(f"  [{i+1:02d}] [DRY] {cat_name} 「{title[:45]}...」")
                created += 1
                continue

            try:
                resp = requests.post(
                    f"{self.api}/posts",
                    json=payload,
                    auth=self.auth,
                    headers=self.headers,
                    timeout=30,
                )
                self._check(resp, f"記事作成 #{i+1}")
                post_id = resp.json()["id"]
                post_url = f"{self.base_url}/?p={post_id}"
                marker = "🔗X埋め込みあり " if i == 0 else ""
                print(f"  [{i+1:02d}] ✓ {marker}{cat_name}  ID={post_id}")
                print(f"        「{title[:50]}」")
                print(f"         {post_url}")
                created += 1
            except Exception as e:
                print(f"  [{i+1:02d}] ✗ {cat_name} 「{title[:40]}...」")
                print(f"       エラー: {e}")
                failed += 1

        print()
        print(f"  完了: {created}件作成 / {skipped}件スキップ / {failed}件失敗")

        if created > 0 and not self.dry_run:
            print()
            print("  ── Xカード表示の確認 ──")
            print("  1本目の試合速報記事にXポスト埋め込みを挿入しました。")
            print("  記事を開いてXカードが表示されることを確認してください。")
            print()
            print("  表示されない場合の対処:")
            print("  ① WP管理画面 → 設定 → メディア → oEmbed が有効か確認")
            print("  ② 記事編集画面で埋め込みURLを再挿入（ブロックを削除→再追加）")
            print("  ③ URLを実在のXポストに差し替え:")
            print(f"     現在のURL: {X_TEST_URL}")
            print("     例: https://x.com/yomiuri_giants/status/（最新ポストIDに差し替え）")
        print()


# ──────────────────────────────────────────────────────────────────
# エントリーポイント
# ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="yoshilover テスト記事10本作成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python3 src/create_test_posts.py              # 公開状態で10本作成
  python3 src/create_test_posts.py --draft      # 下書きで作成
  python3 src/create_test_posts.py --dry-run    # 確認のみ
        """,
    )
    parser.add_argument("--draft",   action="store_true", help="下書き（draft）で作成")
    parser.add_argument("--dry-run", action="store_true", help="確認のみ（変更なし）")
    args = parser.parse_args()

    status = "draft" if args.draft else "publish"
    creator = TestPostCreator(dry_run=args.dry_run, status=status)
    creator.create_posts()


if __name__ == "__main__":
    main()
