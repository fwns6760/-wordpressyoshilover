"""392: ヨシラバー branding X 投稿案を Gemma 4 + Tavily HTTP REST で生成。

391 (Phase 1 CLI) で smoke 確認した方法を本番 ``x-post-mail-lane`` に
組み込むための core モジュール。 stdio MCP ではなく **Tavily REST direct**
を採用 (既存 ``Dockerfile.x_post_mail`` に Node を追加せず、 image / cold
start 不変)。

設計方針 (2026-05-19 user lock):

- 検索は ``POST https://api.tavily.com/search`` で HTTP REST 直叩き。
  fastmcp / Node は使わない。
- 生成は Gemini API 経由 Gemma 4 31B (free tier)。 paid 切替禁止。
- spec 382 hard rule (URL / hashtag / 未検証数字 / 引用 / 媒体名 禁止) を
  system prompt + post-gen regex validator の二段で gate。
- 失敗時は ``None`` 返却 (silent skip)。 caller (``run_x_post_mail.py``) は
  既存 mail を絶対に止めない。
- 任意で ``insight.db`` 由来の DB 照合済み数字を RAG として注入できる。
"""

from __future__ import annotations

import hashlib as _hashlib
import json as _json
import logging as _logging
import re as _re
from typing import Optional

# 既存 ``x_post_mail_lane`` の Candidate / 共通 helper を再利用する。
from src.x_post_mail_lane import (
    Candidate,
    X_CHAR_LIMIT,
    _finalize_post_text,
    _is_safe_post_text,
    _is_verified_full_giants_player_name,
)


# Gemini API 経由 Gemma 4 31B model id (391 smoke で動作確認済)
_GEMMA_BRANDING_METRIC = "GEMMA_BRANDING"
_GEMMA_BRANDING_MODEL = "gemma-4-31b-it"


# spec 382 hard rule の追加 gate (既存 ``_FORBIDDEN_POST_TERMS`` の上に積む)
_GEMMA_BRANDING_FORBIDDEN_PATTERNS = (
    _re.compile(r"https?://"),
    _re.compile(r"#\S+"),
    _re.compile(r"ヨシラバー(で|を|に)?整理しました"),
    _re.compile(r"Xでは|X上では|みんなの声"),
    # 414 axis 1 (2026-05-20): \d+位 を一律 drop (user 報告 岸田 28位 hallucination 事例)
    _re.compile(r"\d+位"),
    # 414 axis C3: 打率 / 出塁率 / OPS / 防御率 系 rate 数字を drop
    # 未検証の rate 数字は spec 382 違反、 Gemma が prompt 破った時の safety net
    # `.345` (1軍打率風) と `3.456` (OPS 風) 両方カバー、 防御率は別 pattern。
    _re.compile(r"(?<!\d)\.\d{3}"),
    _re.compile(r"\d+\.\d{3}"),
    _re.compile(r"防御率\s*\d+\.\d{1,2}"),
)

# 414 axis D (2026-05-20): 炎上・ズレ防止 6 check。 brand identity =「ポジティブな
# 巨人ファン account」 維持のため、 強批判 / 断定 / 雑批判 / 監督批判 / 誤字 / 煽り の
# 6 軸を post-gen 段で drop する。 safety_check で _GEMMA_BRANDING_FORBIDDEN_PATTERNS
# と一緒に評価される (= 同等 hard rule)。
_GEMMA_BRANDING_INFLAMMATORY_PATTERNS = (
    # D1: 強批判語 (選手批判が強すぎる)
    _re.compile(r"使えない|戦犯|クビ|最悪|酷い|論外|引退しろ|辞めろ|無能"),
    # D3: 断定語 (事実超え断定、 brand voice の柔らかさ維持)
    _re.compile(r"絶対|間違いなく|確実に|100%|必ず|断言"),
    # D6: 他球団 / 相手ファン煽り
    _re.compile(r"雑魚|カモ|負け犬|三流|お粗末|情けない|レベルが低い"),
    # D4: 監督批判の雑な隣接 (監督名 + 強批判語)
    # 「阿部監督 無能」「監督 解任」 のような直接批判
    _re.compile(r"(?:監督|采配|阿部)[^\n]{0,15}(?:無能|解任|更迭|降ろせ|失格|無策)"),
    # D5: 偽名 / generic player 表現 (Gemma が roster にない名前 / generic を出した時)
    # 「打者A」「投手X」 等 placeholder 系を drop
    _re.compile(r"打者[A-Z]|投手[A-Z]|選手[A-Z]|プレイヤー[A-Z]"),
)


# 411 (2026-05-20): 本 prompt は フーガ (@EH87EazmV9D2eSw、 巨人ファン長文分析)
# voice の few-shot prompt。 缶詰 (@kandume92、 巨人ファン試合中実況) voice は
# _SYSTEM_PROMPT_KANDUME 側で定義し、 試合日 18-21時のみ select_branding_persona
# で切替える。
_SYSTEM_PROMPT_FUUGA = """あなたは熱心な巨人ファンとして X 投稿案を書きます。
編集者ぶった俯瞰や煽りではなく、 実際に試合を見て一喜一憂しているファンの
voice で、 巨人の今を語ってください。 Tavily で巨人関連トピックを web 検索し、
X 投稿案を 1 件生成してください。

制約 (hard rule、 違反したら出力しないこと):
- 媒体名・記事 URL・hashtag・「ヨシラバーで整理しました」を含めない
- 未検証の数字・引用・順位・打率・防御率・OPS・本塁打数・打点・回数を含めない
- DB 照合できない数字は generalize する (例: 「打率.160」→「打率の数字」)
- 記事タイトルのコピー禁止、 ファンらしい独自の言い回しで書く
- **長さ目安: 220-280 文字** (X 投稿上限 280 字をできるだけ使い切る、 短くまとめない、 観点を厚く積む)
- **140 字未満の薄い post は禁止** (具体観点 + 試合運び + 数字感 + ファン感情を最低 3 軸盛り込む)
- 巨人以外の球団選手の話題は除外
- 公開済み MLB の元巨人 OB (菅野・岡本等) は OK、 非元巨人 MLB は NG
- **【414 hard rule、 厳守】 順位表現 / rate 数字は出力禁止**:
  - **BAD**: 「出塁率28位」 「打率3位」 「歴代5位」 「セ・リーグOPS2位」 「.345」 「防御率1.85」
  - **GOOD**: 「出塁率の数字いい」 「打率は安定」 「歴代でも上位」 「セで上の方」 「数字を残してる」
  - 違反したら出力全体破棄。 「◯位」 という表現は **どんな文脈でも禁止**
- **【414 axis D、 炎上・ズレ防止】 以下も出力禁止 (ポジティブな巨人ファン account 維持のため)**:
  - 強批判語: 「使えない」 「戦犯」 「クビ」 「最悪」 「酷い」 「論外」 「引退しろ」 「辞めろ」 「無能」
  - 断定語: 「絶対」 「間違いなく」 「確実に」 「100%」 「必ず」 「断言」 (= 事実超え断定)
  - 監督批判の雑な隣接: 「阿部監督 無能」 「監督 解任」 「采配 失格」 系
  - 他球団 / 相手ファン煽り: 「雑魚」 「カモ」 「負け犬」 「三流」 「お粗末」 「情けない」
  - 「打者A」 「投手X」 等 generic placeholder 名 (= roster 名で書く)
  - 違反したら出力全体破棄

トーン (重要):
- **本物の巨人ファンらしく**: 連勝の喜び、 優勝争いへの期待、 特定選手への信頼、 悔しさ、 「噛み締める」 テンション、 「ガチで凄い」「とんでもない」 等の素直な熱量、 内輪ネタ (栄冠は君に輝く 等) は自然に出してよい。 ファンとして堂々と巨人寄りで書く
- 編集者ぶった俯瞰目線・「客観中立」 ぶりは NG。 「全野球ファンに公平に伝える」 トーンではなく、 巨人を見続けてきたファンが書いた感を残す
- ただし編集者が装った煽り定型語は禁止: 「ついに」「我が軍」「連覇のピース」「待ち望んでいた」「物語がここから始まる」「その時が来た」「核心に迫る」「いよいよ」 は使わない (これは本物のファンが使わない、 媒体煽り語彙)
- 具体観点を 2〜3 個 厚く入れる (打撃の質、 守備位置の意味、 起用法、 対戦相手との相性、 数字の傾向、 直近の成績推移、 ブルペン事情、 連勝中の試合運び 等)。 単なる気持ちだけ・1 軸だけの薄い post は避ける
- 「あつい」 = 熱量と観点の両立。 ファンの素直な反応 + データ / 起用 / 試合運び / 直近の流れ等の具体観点

【参考: 本物の巨人ファン X 投稿例】
これらの vocabulary / リズム / 改行 / 感嘆詞の出し方を参考にしてください。
内容はその日の DB fact line に合わせて書き換えること (例の数字や選手名は voice
例示であって literal copy 禁止)。

例1 (試合後・連勝中):
```
完勝！ 7連勝！！
戸郷ナイスピッチ！

こんなに勝ちが続くなんていつ以来やろ

ピッチャーのクオリティが高すぎる
あまり打たれる気がしない
完全に優勝争いに入ったな

主力に怪我出なければ
栄冠は君に輝くわ とか戸郷-中川-瑛斗-大勢
ナイスー！！

平山初回先頭打者
ダルベック-大城！
門脇の守備！

7連勝です！ とんでもないことです
マジ7連勝はガチ凄い
次は8月辺りまで中々無いかもしれない、 噛み締めましょう
```

例2 (試合前・展望):
```
明日、 DeNAに勝って3連勝
来週のヤクルトに2連勝
来週末のドームの阪神に勝ち越し

もし奇跡的にいけたら
俺マジックは点灯する

それぐらい最近いい戦いしてる
投打が噛み合ってる
```

voice の特徴 (例から学ぶべきもの):
- 短い感嘆文 + 連続改行で気持ちを並べる
- 選手 nickname / 名字のみ (戸郷さん / 瑛斗 / 大勢 等) を自然に出す
- 数字を自分の言葉で言う (連勝数 / イニング / 失点等、 ただし DB fact 内のみ)
- 「ガチ凄い」「とんでもない」「噛み締める」 等の素直な感嘆
- 仮定で先まで描く (「もし〜いけたら」「主力に怪我なければ」)
- 比較で深さを出す (「いつ以来やろ」「次は8月辺りまで」)
- 「ナイスー！！」 みたいな感嘆詞のみの行 OK
- 内輪ネタ (栄冠は君に輝く 等) 自然に
- 280 字以内で観点も厚く

時系列制約 (重要):
- Tavily snippet の日付を必ず確認する。 1 週間以上前 / 日付不明 / 復帰前提・開幕直後 など過去文脈の snippet では、 「ついに」「これから」「もうすぐ」「いよいよ」 等の未来形・直近形を使わない
- 古い snippet しか無い場合は、 一般的な傾向 / 過去の経緯 / 起用の文脈 として淡々と書く。 現在進行形・直近形で書かない
- 季節 / 開幕 / 復帰 等の文脈は snippet 日付と現在 ({today_jst}) の差を踏まえて慎重に扱う
- DB fact line (今日試合 / player log / 連勝記録) は verified なので、 そのまま事実として使ってよい (むしろ積極的に使う)

時間帯トーン ({hour_jst} 時 JST):
{time_tone_hint}

出力形式: post 本文のみ。 説明や前置きは書かない。 例の literal コピー禁止、
voice の特徴だけ学んで今日の事実で書く。
"""


_SYSTEM_PROMPT_KANDUME = """あなたは熱心な巨人ファンとして X 投稿案を書きます。
試合中の実況視点で、 短文を改行で連投する形で書きます。 一喜一憂しながら、
今この瞬間の試合状況を共有する感覚で投稿してください。 Tavily で巨人関連の
直近トピックを web 検索し、 試合中の臨場感ある投稿案を 1 件生成してください。

制約 (hard rule、 違反したら出力しないこと):
- 媒体名・記事 URL・hashtag・「ヨシラバーで整理しました」を含めない
- 未検証の数字・引用・順位・打率・防御率・OPS・本塁打数・打点・回数を含めない
- DB 照合できない数字は generalize する (例: 「打率.160」→「打率の数字」)
- 記事タイトルのコピー禁止、 ファンらしい独自の言い回しで書く
- **長さ目安: 180-280 文字** (短文連投が缶詰 voice の核、 1 行 1 観点で改行を多用)
- **140 字未満の薄い post は禁止** (試合状況 + 選手反応 + 次への期待 を最低 3 観点)
- 巨人以外の球団選手の話題は除外
- 公開済み MLB の元巨人 OB (菅野・岡本等) は OK、 非元巨人 MLB は NG
- **【414 hard rule、 厳守】 順位表現 / rate 数字は出力禁止**:
  - **BAD**: 「出塁率28位」 「打率3位」 「歴代5位」 「セ・リーグOPS2位」 「.345」 「防御率1.85」
  - **GOOD**: 「出塁率いいね」 「打率いい感じ」 「歴代でも上位」 「ピッチャーの数字いい」
  - 違反したら出力全体破棄。 「◯位」 という表現は **どんな文脈でも禁止**
- **【414 axis D、 炎上・ズレ防止】 以下も出力禁止 (ポジティブな巨人ファン account 維持のため)**:
  - 強批判語: 「使えない」 「戦犯」 「クビ」 「最悪」 「酷い」 「論外」 「引退しろ」 「辞めろ」 「無能」
  - 断定語: 「絶対」 「間違いなく」 「確実に」 「100%」 「必ず」 「断言」
  - 監督批判の雑な隣接: 「阿部監督 無能」 「采配 失格」 系
  - 他球団 / 相手ファン煽り: 「雑魚」 「カモ」 「負け犬」 「三流」
  - 「打者A」 「投手X」 等 generic placeholder 名
  - 違反したら出力全体破棄

トーン (重要):
- **試合中実況の voice**: 「◯回終わって◯-◯」「次の打席◯◯」「この回しのげれば」「来た！」「ここでこの場面!」 のような実況・実感の voice
- **短文連投・改行多用**: 1 文を短く、 改行で並べる。 長い分析文 1 個より、 短い反応 4-5 個を改行で並べる方が缶詰 voice らしい
- 編集者ぶった俯瞰・「客観中立」 は NG。 試合を見ながら呟いている感じ
- 媒体煽り定型語 (「ついに」「我が軍」「連覇のピース」「待ち望んでいた」「物語がここから始まる」「その時が来た」「いよいよ」) は使わない
- 試合中なので 「勝った」「連勝確定」 を完了形で言わない (まだ続行中)。 「この回踏ん張れば」「次のイニング次第」 等、 流動的な書き方
- 数字は DB fact のみ (今日の試合進行 / 選手 stat) を使う

【参考: 本物の巨人ファン試合中実況 X 投稿 voice (缶詰系)】
これらの語彙・改行・短文リズムを参考にしてください。 内容は今日の DB fact /
Tavily 直近情報に合わせて書き換えること (literal copy 禁止)。

例1 (試合中・接戦):
```
4回終わって 2-2

戸郷さんようやくリズム掴んできた
3回までは球が高かったけど
4回はギア入ったわ

問題は打線
あの場面で1点取れないのは痛い
6番までで残塁8

次の回頭からクリーンアップ
ここで一発欲しい
```

例2 (試合中・リード時):
```
7回終わって 4-1

中川-瑛斗の継投完璧
バックも固い

打線は3回の集中打が効いてる
門脇のセーフティが起点
これが繋がる野球やね

あと2回
大勢に繋げたい
ここからの2イニング集中
```

例3 (試合中・劣勢時):
```
6回終わって 1-4

ピッチャーが捕まりだしたな
連打されるとキツい

打線も合ってない感じ
相手先発のキレが落ちる時を待つしか

残り3イニング
1点ずつでも返したい
諦めるには早い
```

voice の特徴 (例から学ぶべきもの):
- 試合進行 (◯回終わって ◯-◯) を冒頭に置く
- 短文を改行で並べる (1 行 1 観点)
- 投手・打線・守備 を分けてコメント
- 次の展開への期待・不安を最後に置く
- 「ようやくリズム掴んできた」「合ってない感じ」 のリアルタイム観察
- 「ここで」「次の回」「あと◯回」 の即時性
- 280 字以内で短文連投の臨場感

時系列制約 (重要):
- 試合中前提。 試合中の DB fact (今日の試合進行) があれば積極的に使う
- Tavily snippet が古い場合は時系列を曖昧にせず、 試合中の臨場感だけに focus
- まだ試合終了確定前なので「勝った」「連勝」 を完了形で言わない
- 季節 / 開幕 / 復帰 等の文脈は今 ({today_jst}) との時間差を踏まえる

時間帯トーン ({hour_jst} 時 JST):
{time_tone_hint}

出力形式: post 本文のみ。 説明や前置きは書かない。 例の literal コピー禁止、
voice の特徴だけ学んで今日の事実で書く。
"""


def _build_system_prompt(now_jst_hour: int, today_jst: str, *, persona: str = "fuuga") -> str:
    """時間帯 hint を生成する。

    411 (2026-05-20): persona 引数で フーガ (長文分析) / 缶詰 (試合中実況) を切替。
    persona "fuuga" (default) = _SYSTEM_PROMPT_FUUGA、
    persona "kandume" = _SYSTEM_PROMPT_KANDUME。
    unknown persona は fuuga にフォールバック (silent fallback、 安全側)。

    重要: voice (few-shot 例の語彙 / リズム / 改行 / 感嘆詞) は persona ごとに
    固定。 hint は **content** (何を書くか) と **熱量の出し方** だけを時間帯に
    合わせて変える。
    """
    if 5 <= now_jst_hour < 11:
        hint = (
            "【朝 5-11 時】\n"
            "- content: 昨日の試合の余韻 / 連勝中の流れ / 今日試合への期待 / 先発予想\n"
            "- 熱量: 静かに。 「噛み締めながら今日も〜」「昨日のあの瞬間〜」 みたいな softer 寄り\n"
            "- voice (例の語彙・リズム) は維持、 ただし「ガチ凄い」 連発はしない"
        )
    elif 11 <= now_jst_hour < 17:
        hint = (
            "【昼〜午後 11-17 時】\n"
            "- content: 今日試合前の話題 / lineup / 先発投手 / 起用 / 直近の流れ / data の傾向\n"
            "- 熱量: 落ち着いた中での期待感。 まだ試合中じゃないので「勝った！」 系の祝杯 voice は使わない\n"
            "- 試合データやニュース記事 (Tavily snippet) を素材に、 ファン目線で読み解く"
        )
    elif 17 <= now_jst_hour < 22:
        hint = (
            "【試合直前〜試合中 17-22 時】\n"
            "- content: 試合直前の期待 / スタメン / 先発 / 試合中なら現時点までの展開 (DB fact にあれば)\n"
            "- 熱量: ワクワク・緊張・期待。 「今夜は〜」「先発の戸郷さんが〜」 みたいな前のめり\n"
            "- 試合終了確定前なので「勝った」「連勝」 を完了形で言わない。 まだ continued。 試合中のテンションで"
        )
    else:
        hint = (
            "【試合後・深夜 22 時以降〜朝 5 時】\n"
            "- content: 試合結果 / player の今日 stat / 連勝記録 / 余韻\n"
            "- 熱量: 例示そのままの祝杯 / 悔しさ voice 全開。 「完勝！」「ガチ凄い」「噛み締めましょう」「とんでもない」 OK\n"
            "- DB fact line の今日 stat (6回1失点 8K 等) を堂々と使う。 verified 数字"
        )
    template = _SYSTEM_PROMPT_KANDUME if persona == "kandume" else _SYSTEM_PROMPT_FUUGA
    return template.format(
        hour_jst=now_jst_hour,
        today_jst=today_jst,
        time_tone_hint=hint,
    )


def is_giants_game_day(now_jst, db_path: str) -> bool:
    """411 (2026-05-20): 今日 (now_jst の JST 日付) に巨人試合があるか.

    insight.db の `games` テーブルを `SELECT 1 FROM games WHERE game_date = ?` で
    判定。 row が 1 つ以上あれば True、 0 なら False。
    db_path 不正 / sqlite open 失敗 / SELECT 例外時は False (silent fallback、
    安全側 = 試合無いと見なし 缶詰 persona を発火させない)。
    """
    if not db_path:
        return False
    try:
        today = now_jst.strftime("%Y-%m-%d")
    except Exception:
        return False
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT 1 FROM games WHERE game_date = ? LIMIT 1",
                (today,),
            )
            row = cur.fetchone()
        finally:
            con.close()
        return row is not None
    except Exception:
        return False


def select_branding_persona(now_jst, is_game_day: bool) -> str:
    """411 (2026-05-20): persona 自動選択.

    user 仕様 lock:
    - 試合日 + 18-21 時 JST = 缶詰 (試合中実況 voice)
    - それ以外 (非試合日 / 試合日でも時間外) = フーガ (長文分析 voice)

    Returns 'kandume' or 'fuuga'.
    """
    try:
        hour = int(now_jst.hour)
    except Exception:
        return "fuuga"
    if is_game_day and 18 <= hour <= 21:
        return "kandume"
    return "fuuga"


# 414 axis A (2026-05-20): user spec lock 5 型分離.
# 観戦中 (試合中) は 感情系 + 次の展開系 が強い。
_POST_TYPES = ("flash", "emotion", "data", "next", "positive")

_POST_TYPE_GUIDANCE: dict[str, str] = {
    "flash": (
        "【今回の型: 速報系】\n"
        "- 事実中心: 選手名 / 回 / スコア を厳格に書く。 DB fact / Tavily literal に\n"
        "  ないものは書かない\n"
        "- 短文 OK、 観点 1-2 個に絞ってよい (長文無理に書かない)\n"
        "- 感想は控えめ、 事実が主"
    ),
    "emotion": (
        "【今回の型: 感情系】\n"
        "- 巨人ファンの気持ち代弁 (噛み締める / 嬉しい / 悔しい / ホッとした 等)\n"
        "- 数字は 1 個だけでも、 そこから派生する感情を厚く\n"
        "- 「同じ条件で並べると」 系の分析調は控え、 ファンの本音 voice"
    ),
    "data": (
        "【今回の型: データ系】\n"
        "- 過去成績 / 直近傾向 を踏まえる (ただし順位は絶対書かない = axis C1)\n"
        "- 「最近のリズム」「打順上位の働き」 等の傾向観察として書く\n"
        "- 数字は DB fact 由来のみ、 generalize OK"
    ),
    "next": (
        "【今回の型: 次の展開系】\n"
        "- 試合進行中前提 (まだ続行中、 完了形で書かない)\n"
        "- 采配 / 継投 / 追加点 / 守備固め / 代打 / 抑え への期待・想像\n"
        "- 「ここで」「次の回」「あと◯回」 の即時性、 流動的な書き方"
    ),
    "positive": (
        "【今回の型: ポジティブ系】\n"
        "- 若手 / 二軍 / 復帰選手 / 育成 を拾う (やってる感、 期待感)\n"
        "- 「いいな」「楽しみ」「これからの選手」 voice\n"
        "- 強批判 / 雑批判 NG (axis D 厳守)"
    ),
}


def select_post_type(
    now_jst,
    is_game_day: bool,
    has_db_fact: bool = False,
    has_tavily_results: bool = False,
) -> str:
    """414 axis A: 型自動選択.

    user 仕様 lock (2026-05-20 chat):
    - 観戦中 (試合日 18-21時) = next (次の展開系) 優先、 fallback emotion
    - 試合後 (試合日 22-23時) = emotion (試合の余韻)
    - 試合日 朝 (5-11時) = data (前日試合の余韻 + 今日試合への準備)
    - 試合日 昼 (11-17時) = data + emotion (試合前 buildup)
    - 非試合日 朝 = data (前日試合 stat / 直近傾向)
    - 非試合日 昼 = positive (若手 / 二軍 narrative)
    - 非試合日 夜 = emotion (off-day fan voice)
    - flash は test 用 / caller override 用、 自動選択は使わない (= 事実中心は型に
      しなくても axis C で hallucination 防止が効くため)

    Returns one of: 'next' / 'emotion' / 'data' / 'positive' / 'flash'
    """
    try:
        hour = int(now_jst.hour)
    except Exception:
        return "emotion"
    if is_game_day:
        if 18 <= hour <= 21:
            return "next"
        if 22 <= hour <= 23 or hour < 5:
            return "emotion"
        if 5 <= hour < 11:
            return "data"
        if 11 <= hour < 17:
            return "data" if has_db_fact else "emotion"
        # hour 17: 試合直前
        return "next"
    # 非試合日
    if 5 <= hour < 11:
        return "data"
    if 11 <= hour < 17:
        return "positive"
    return "emotion"


# 411 (2026-05-20): user 仕様 = 公式 / NPB / 球団 / 主要スポーツ紙を優先。
# include_domains で Tavily 側の取得を whitelist 内に絞る。 paid credit / cost は
# domain 数によらず 1 query = 1 credit (free tier 1000/月 内で運用)。
_TAVILY_INCLUDE_DOMAINS = (
    # 公式 / 球団
    "giants.jp",
    "npb.or.jp",
    # 主要スポーツ紙
    "hochi.news",
    "sponichi.co.jp",
    "nikkansports.com",
    "sanspo.com",
    "daily.co.jp",
    "chunichi.co.jp",
    # ポータル (既存)
    "sports.yahoo.co.jp",
)


def _tavily_search(
    query: str,
    api_key: str,
    *,
    max_results: int = 3,
    timeout_seconds: int = 30,
    same_day_only: bool = False,
) -> list[dict]:
    """Tavily REST API 検索 (日本 sport 記事のみ)。

    Yahoo Japan sport + 報知 に絞って巨人関連の新鮮な記事だけ拾う。
    全 web 検索だと SF Giants (MLB) / NBA / 関係ない海外 sport が混入
    して Gemma が hallucinate するため domain 限定 (2026-05-20 fix)。

    days=2 で前日+当日のみ。 same_day_only=True にすれば JST 当日 only
    (test 用)、 default は False (朝 fire で前夜試合の記事を拾えるよう
    に)。 0 件返却なら caller は no context として silent skip する。
    """
    if not query or not api_key:
        return []
    try:
        import requests
        # 411 (2026-05-20): user 仕様 = Tavily の `answer` は使わない、
        # `results[].url` / `title` / `content` / `published_date` だけを見る。
        # include_answer=False を明示 (default も False だが spec lock として明示)。
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "topic": "news",
                "days": 2,
                "include_domains": list(_TAVILY_INCLUDE_DOMAINS),
                "include_answer": False,
            },
            timeout=timeout_seconds,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    results = data.get("results")
    if not isinstance(results, list):
        return []
    if not same_day_only:
        return results
    return _filter_same_day_jst(results)


def _filter_same_day_jst(results: list[dict]) -> list[dict]:
    """JST 当日 published のものだけ残す。

    published_date は Tavily news topic で RFC 1123 (例: "Tue, 19 May 2026
    13:30:00 GMT") で返ることが多いが、 形式不明 / parse 失敗時は除外する
    (silent fallback、 hallucination 抑制を優先)。
    """
    from datetime import datetime, timezone, timedelta
    from email.utils import parsedate_to_datetime
    jst = timezone(timedelta(hours=9))
    today_jst = datetime.now(jst).date()
    kept: list[dict] = []
    for r in results:
        raw = r.get("published_date") or ""
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt.astimezone(jst).date() == today_jst:
                kept.append(r)
        except (TypeError, ValueError):
            continue
    return kept


def _gemma_branding_safety_check(text: str) -> bool:
    """spec 382 hard rule gate for Gemma branding output.

    True = safe (pass). False = violation (caller drops the candidate)。
    414 axis D: 炎上 / ズレ防止 patterns も同等 hard rule として評価。
    """
    if not text or not text.strip():
        return False
    if len(text) > X_CHAR_LIMIT:
        return False
    for pattern in _GEMMA_BRANDING_FORBIDDEN_PATTERNS:
        if pattern.search(text):
            return False
    # 414 axis D: 炎上系も同 fail 扱い
    for pattern in _GEMMA_BRANDING_INFLAMMATORY_PATTERNS:
        if pattern.search(text):
            return False
    if not _is_safe_post_text(text):
        return False
    return True


def _matched_inflammatory_pattern(text: str) -> Optional[str]:
    """414 axis D + C7 log: text が炎上 pattern に hit した場合、 hit した
    pattern 文字列を返す (drop log に reason として記録するため)。 hit なしは None。
    """
    for pattern in _GEMMA_BRANDING_INFLAMMATORY_PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    return None


# 414 axis 2 (2026-05-20): 数値 whitelist helper.
# verified_text (db_fact + Tavily content の連結) に literal 出現しない数字を
# unverified としてリストする。 1 件でもあれば caller は candidate を drop。
# 「verified set 内なら hallucination ではない」 という保守的判定 (false-negative
# 寄り = 多めに drop)。
_NUMERIC_TOKEN_RE = _re.compile(r"\d+(?:\.\d+)?")


def _extract_unverified_numbers(text: str, verified_text: str) -> list[str]:
    """text 内の数字 token のうち verified_text に literal 出現しないものを返す.

    生成 text から `\\d+(?:\\.\\d+)?` で数字 (整数 + 小数) を抽出。 各数字が
    verified_text の substring として現れない場合 unverified。 verified_text には
    db_fact_line と Tavily 検索結果の content / title を連結したものを caller が
    渡す想定 (414 axis 2 hallucination 防止)。
    """
    if not text:
        return []
    safe_verified = verified_text or ""
    found: list[str] = []
    for match in _NUMERIC_TOKEN_RE.finditer(text):
        token = match.group(0)
        if token not in safe_verified:
            found.append(token)
    return found


# 414 axis 6 (2026-05-20): published_date 7日超過 entry を context から drop.
# 現状 _format_tavily_context は全 entry を Gemma に渡しており、 古い snippet の
# 「ついに」「これから」 を Gemma が現在化する事故が起きうる。 朝 fire で前日試合
# 記事は欲しい (1 日前は残す) ので default 7 日 (= 1 週間) に。
def _recent_published_within_days(results: list[dict], days: int = 7) -> list[dict]:
    """published_date が直近 days 日以内の entry のみを返す.

    parse 失敗 / date 不明の entry は **残す** (false-negative 寄り、 caller の
    Gemma context に注入される、 prompt 制約で 「日付不明は淡々と書く」 と既に指示)。
    days <= 0 なら same-day-only モード (414 axis 9 と同等)。
    """
    if not results:
        return []
    from datetime import datetime, timezone, timedelta
    from email.utils import parsedate_to_datetime
    jst = timezone(timedelta(hours=9))
    today_jst = datetime.now(jst).date()
    cutoff = today_jst - timedelta(days=max(0, days))
    kept: list[dict] = []
    for r in results:
        raw = r.get("published_date") or ""
        if not raw:
            # 日付不明: 残す (false-negative 寄り)
            kept.append(r)
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            entry_date = dt.astimezone(jst).date()
        except (TypeError, ValueError):
            # parse 失敗: 残す
            kept.append(r)
            continue
        if days <= 0:
            if entry_date == today_jst:
                kept.append(r)
        elif entry_date >= cutoff:
            kept.append(r)
    return kept


def build_db_fact_line(
    player_canonical: str,
    db_path: str,
    *,
    target_date: Optional[str] = None,
    streak_window: int = 5,
) -> str:
    """``insight.db`` から today の試合 / player stat / 直近連勝 を 1 fact line に。

    Read-only SELECT only。 DB に該当 record が無ければ各 line を skip、
    全件無ければ空 string を返す (Gemma 側で「DB fact 注入: なし」 扱い)。

    formats (改行区切り、 全部 facts のみ、 narrative なし):
        - 今日(YYYY-MM-DD) 巨人 vs OPP: GS-OS WIN/LOSS/DRAW
        - PLAYER 打撃: AB打数 H安打 HR本塁打 RBI打点 (today)
        - PLAYER 投球: IP回 R失点 K奪三振 (result_mark) (today)
        - 直近N試合: ○●○●○ (W3-L2)
    """
    if not player_canonical or not db_path:
        return ""
    from datetime import datetime, timezone, timedelta
    jst = timezone(timedelta(hours=9))
    today = target_date or datetime.now(jst).strftime("%Y-%m-%d")
    lines: list[str] = []
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = con.cursor()

            cur.execute(
                "SELECT game_id, opponent, giants_score, opp_score, result "
                "FROM games WHERE game_date = ? AND giants_score IS NOT NULL "
                "ORDER BY ingested_at DESC LIMIT 1",
                (today,),
            )
            game_row = cur.fetchone()
            today_game_id: Optional[str] = None
            if game_row:
                today_game_id, opp, gs, op_s, res = game_row
                res_jp = {
                    "win": "勝利",
                    "loss": "敗戦",
                    "draw": "引分",
                }.get((res or "").lower(), "")
                score = (
                    f"{gs}-{op_s}"
                    if gs is not None and op_s is not None
                    else ""
                )
                game_parts = [f"今日({today}) 巨人 vs {opp}"]
                if score:
                    game_parts.append(score)
                if res_jp:
                    game_parts.append(f"({res_jp})")
                lines.append("- " + " ".join(game_parts))

            if today_game_id:
                cur.execute(
                    "SELECT AB, H, R, RBI, SB FROM batting_logs "
                    "WHERE game_id = ? AND player_canonical = ? AND team_role = 'giants' "
                    "LIMIT 1",
                    (today_game_id, player_canonical),
                )
                bat = cur.fetchone()
                if bat:
                    ab, h, r, rbi, sb = bat
                    parts = []
                    if ab is not None and h is not None:
                        parts.append(f"{ab}打数{h}安打")
                    if rbi:
                        parts.append(f"{rbi}打点")
                    if r:
                        parts.append(f"{r}得点")
                    if sb:
                        parts.append(f"{sb}盗塁")
                    if parts:
                        lines.append(f"- {player_canonical} 打撃 (今日): " + " ".join(parts))

                cur.execute(
                    "SELECT IP, H_allowed, R, ER, K, BB, result_mark FROM pitching_logs "
                    "WHERE game_id = ? AND player_canonical = ? AND team_role = 'giants' "
                    "LIMIT 1",
                    (today_game_id, player_canonical),
                )
                pit = cur.fetchone()
                if pit:
                    ip, h_a, r, er, k, bb, mark = pit
                    parts = []
                    if ip is not None:
                        parts.append(f"{ip}回")
                    if er is not None:
                        parts.append(f"{er}失点")
                    elif r is not None:
                        parts.append(f"{r}失点")
                    if h_a is not None:
                        parts.append(f"被安打{h_a}")
                    if k:
                        parts.append(f"{k}K")
                    if bb:
                        parts.append(f"{bb}四球")
                    if mark:
                        parts.append(f"({mark})")
                    if parts:
                        lines.append(f"- {player_canonical} 投球 (今日): " + " ".join(parts))

            if streak_window > 0:
                # 直近 loss が出るまで遡って「連勝中」 / 「連敗中」 / 「混在」
                # を集計する。 引き分けは streak を切らない (NPB 慣習)。
                cur.execute(
                    "SELECT game_date, result FROM games "
                    "WHERE game_date <= ? AND result IN ('win', 'loss', 'draw') "
                    "AND giants_score IS NOT NULL "
                    "ORDER BY game_date DESC LIMIT 40",
                    (today,),
                )
                recent = cur.fetchall()
                if recent:
                    # 現在 streak: 最新試合 (recent[0]) の result から start。
                    # win 連続なら 連勝、 loss 連続なら 連敗、 引き分けが先頭
                    # なら 「直近 △ 後の状況」 で扱う。
                    latest_result = (recent[0][1] or "").lower()
                    current_streak_wins = 0
                    current_streak_draws = 0
                    current_streak_losses = 0
                    current_mode: Optional[str] = None
                    for _, r in recent:
                        rl = (r or "").lower()
                        if current_mode is None:
                            if rl == "draw":
                                current_streak_draws += 1
                                continue
                            current_mode = rl
                        if current_mode == "win":
                            if rl == "win":
                                current_streak_wins += 1
                            elif rl == "draw":
                                current_streak_draws += 1
                            else:
                                break
                        elif current_mode == "loss":
                            if rl == "loss":
                                current_streak_losses += 1
                            elif rl == "draw":
                                current_streak_draws += 1
                            else:
                                break
                    streak_phrase = ""
                    if current_mode == "win" and current_streak_wins > 0:
                        streak_phrase = f"現在 {current_streak_wins}連勝中"
                        if current_streak_draws > 0:
                            streak_phrase += f" (間に△{current_streak_draws})"
                    elif current_mode == "loss" and current_streak_losses > 0:
                        streak_phrase = f"現在 {current_streak_losses}連敗中"
                        if current_streak_draws > 0:
                            streak_phrase += f" (間に△{current_streak_draws})"
                    elif current_mode is None and current_streak_draws > 0:
                        streak_phrase = f"直近{current_streak_draws}試合 引き分け続き"
                    if streak_phrase:
                        lines.append(f"- {streak_phrase}")
                    # 直近 streak_window 試合の marks (補助情報)
                    short = recent[: max(streak_window, 5)]
                    marks_short = []
                    for _, r in short:
                        rl = (r or "").lower()
                        if rl == "win":
                            marks_short.append("○")
                        elif rl == "loss":
                            marks_short.append("●")
                        else:
                            marks_short.append("△")
                    if marks_short:
                        lines.append(
                            f"- 直近{len(marks_short)}試合: "
                            + "".join(marks_short)
                        )
        finally:
            con.close()
    except Exception:
        return ""
    return "\n".join(lines)


def build_team_roundup_fact_line(
    db_path: str,
    *,
    target_date: Optional[str] = None,
    top_batter_h_threshold: int = 2,
    top_pitcher_ip_threshold: float = 1.0,
) -> str:
    """勝利後 roundup 用に、 今日試合に絡んだ複数 player の stat をまとめる。

    今日試合が win の時だけ返す。 それ以外 (loss / draw / unknown / no
    game) は空 string。 caller は空なら single-player mode に fallback。

    形式:
        - 今日(YYYY-MM-DD) 巨人 vs OPP: GS-OS 勝利
        - PLAYER1: X打数Y安打 ZHR
        - PLAYER2: X打数Y安打 Z打点
        - PITCHER1: X.Y回 Z失点 K奪三振 (○)
        - PITCHER2: X.Y回 Z失点 K奪三振 (H)
        - 直近5試合: ○●○●○ (X勝Y敗)
    """
    if not db_path:
        return ""
    from datetime import datetime, timezone, timedelta
    jst = timezone(timedelta(hours=9))
    today = target_date or datetime.now(jst).strftime("%Y-%m-%d")
    lines: list[str] = []
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT game_id, opponent, giants_score, opp_score, result "
                "FROM games WHERE game_date = ? AND giants_score IS NOT NULL "
                "ORDER BY ingested_at DESC LIMIT 1",
                (today,),
            )
            row = cur.fetchone()
            if not row:
                return ""
            game_id, opp, gs, op_s, res = row
            if (res or "").lower() != "win":
                return ""
            score = f"{gs}-{op_s}" if gs is not None and op_s is not None else ""
            parts = [f"今日({today}) 巨人 vs {opp}"]
            if score:
                parts.append(score)
            parts.append("勝利")
            lines.append("- " + " ".join(parts))

            cur.execute(
                "SELECT player_canonical, AB, H, RBI, R, SB FROM batting_logs "
                "WHERE game_id = ? AND team_role = 'giants' AND H >= ? "
                "ORDER BY H DESC, RBI DESC LIMIT 5",
                (game_id, top_batter_h_threshold),
            )
            for player, ab, h, rbi, r, sb in cur.fetchall():
                if not player:
                    continue
                bat_parts = []
                if ab is not None and h is not None:
                    bat_parts.append(f"{ab}打数{h}安打")
                if rbi:
                    bat_parts.append(f"{rbi}打点")
                if r:
                    bat_parts.append(f"{r}得点")
                if sb:
                    bat_parts.append(f"{sb}盗塁")
                if bat_parts:
                    lines.append(f"- {player} 打撃: " + " ".join(bat_parts))

            cur.execute(
                "SELECT player_canonical, IP, ER, R, K, BB, H_allowed, result_mark "
                "FROM pitching_logs "
                "WHERE game_id = ? AND team_role = 'giants' AND IP >= ? "
                "ORDER BY appearance_order LIMIT 5",
                (game_id, top_pitcher_ip_threshold),
            )
            for player, ip, er, r, k, bb, h_a, mark in cur.fetchall():
                if not player:
                    continue
                pit_parts = []
                if ip is not None:
                    pit_parts.append(f"{ip}回")
                if er is not None:
                    pit_parts.append(f"{er}失点")
                elif r is not None:
                    pit_parts.append(f"{r}失点")
                if k:
                    pit_parts.append(f"{k}K")
                if bb:
                    pit_parts.append(f"{bb}四球")
                if h_a is not None:
                    pit_parts.append(f"被安打{h_a}")
                if mark:
                    pit_parts.append(f"({mark})")
                if pit_parts:
                    lines.append(f"- {player} 投球: " + " ".join(pit_parts))

            cur.execute(
                "SELECT result FROM games "
                "WHERE game_date <= ? AND result IN ('win', 'loss', 'draw') "
                "AND giants_score IS NOT NULL "
                "ORDER BY game_date DESC LIMIT 40",
                (today,),
            )
            recent = cur.fetchall()
            if recent:
                latest_result = (recent[0][0] or "").lower()
                wins_in_streak = 0
                draws_in_streak = 0
                losses_in_streak = 0
                current_mode: Optional[str] = None
                for (rl,) in recent:
                    rl_lower = (rl or "").lower()
                    if current_mode is None:
                        if rl_lower == "draw":
                            draws_in_streak += 1
                            continue
                        current_mode = rl_lower
                    if current_mode == "win":
                        if rl_lower == "win":
                            wins_in_streak += 1
                        elif rl_lower == "draw":
                            draws_in_streak += 1
                        else:
                            break
                    elif current_mode == "loss":
                        if rl_lower == "loss":
                            losses_in_streak += 1
                        elif rl_lower == "draw":
                            draws_in_streak += 1
                        else:
                            break
                if current_mode == "win" and wins_in_streak > 0:
                    sp = f"現在 {wins_in_streak}連勝中"
                    if draws_in_streak > 0:
                        sp += f" (間に△{draws_in_streak})"
                    lines.append(f"- {sp}")
                elif current_mode == "loss" and losses_in_streak > 0:
                    sp = f"現在 {losses_in_streak}連敗中"
                    if draws_in_streak > 0:
                        sp += f" (間に△{draws_in_streak})"
                    lines.append(f"- {sp}")
        finally:
            con.close()
    except Exception:
        return ""
    # 試合 line + 直近 streak しか無い (player 0 件) なら roundup として
    # 意味薄いので空返却 (caller は single-player にフォールバック)
    if len(lines) < 3:
        return ""
    return "\n".join(lines)


def build_team_roundup_candidate(
    fact_line: str,
    *,
    gemini_api_key: str,
    tavily_api_key: str,
    timeout_seconds: int = 30,
    model_id: str = _GEMMA_BRANDING_MODEL,
    temperature: float = 0.7,
    logger: Optional[_logging.Logger] = None,
) -> Optional[Candidate]:
    """勝利後 roundup post を 1 件返す。

    複数 player を total 化したファン voice の post を生成する。 fact line
    は build_team_roundup_fact_line() で取得済み (空なら caller が roundup
    mode を発火しない)。 Tavily は使わず DB fact + プロンプト指示のみで
    安全に書く (Tavily snippet は player roundup の文脈に弱いため省略)。
    """
    log = logger or _logging.getLogger("x_post_branding_gen")
    if not fact_line.strip() or not gemini_api_key:
        log.info("team_roundup_skip reason=missing_input")
        return None
    from datetime import datetime, timezone, timedelta
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    system_prompt = _build_system_prompt(
        now_jst_hour=now_jst.hour,
        today_jst=now_jst.strftime("%Y-%m-%d"),
    )
    # Yahoo Japan + 報知から試合の news を context として注入
    # (個人選手と違って team / 連勝 / 試合 の話を拾う)
    news_results = _tavily_search(
        "巨人",
        tavily_api_key,
        max_results=5,
        timeout_seconds=timeout_seconds,
        same_day_only=False,
    )
    news_ctx = _format_tavily_context(news_results) if news_results else ""
    prompt_parts = [
        system_prompt,
        "",
        "今日の試合の DB 照合済み数字 (使ってよい数字):",
        fact_line,
        "",
    ]
    if news_ctx:
        prompt_parts.extend([
            "Yahoo Japan + 報知の最新巨人記事 (参考、 引用 / 媒体名 / URL は使わない):",
            news_ctx,
            "",
        ])
    prompt_parts.extend([
        "上記の DB facts + ニュース記事を参考に、 ファンらしく今日の試合を",
        "1 件の roundup post にまとめてください。 投手 / 打者 / 試合運び /",
        "結果 / 連勝 / news で話題になっている観点 を総括する。",
        "個別 stat を一行ずつ淡々と書かず、 ファン voice で短い感嘆 + 観点。",
        "選手名は DB か news に出てきた選手のみ。 出てない選手を勝手に書かない。",
    ])
    prompt = "\n".join(prompt_parts)
    try:
        from google import genai
        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config={"temperature": temperature},
        )
        text = (getattr(response, "text", None) or "").strip()
    except Exception as exc:  # noqa: BLE001 - silent skip per fault tolerance
        log.warning("team_roundup_skip reason=gemini_error err=%r", exc)
        return None
    text = _finalize_post_text(text)
    if not _gemma_branding_safety_check(text):
        log.warning(
            "team_roundup_skip reason=safety_check_failed text_preview=%r",
            text[:60],
        )
        return None
    signature_hash = _hashlib.sha1(
        f"team_roundup|{today_str(now_jst)}|{text[:80]}".encode("utf-8")
    ).hexdigest()[:16]
    draft_lines = [
        "【根拠: Gemma 4 team roundup + DB fact】",
        "対象: 今日の勝利試合 (複数選手 total)",
        f"model: {model_id}",
        "",
        "【DB fact line】",
        fact_line,
    ]
    log.info("team_roundup_candidate_built text_len=%d", len(text))
    return Candidate(
        title=f"Gemma 4 試合後 roundup",
        metric=_GEMMA_BRANDING_METRIC,
        period_label="試合後 roundup",
        draft_text="\n".join(draft_lines),
        post_text=text,
        char_count=len(text),
        signature=f"team_roundup|{signature_hash}|False|None",
        focus_player="(roundup)",
        source_material_type="gemma_branding",
    )


def today_str(now_jst) -> str:
    """Helper for signature hashing (separate function to keep build_team_roundup_candidate readable)."""
    return now_jst.strftime("%Y-%m-%d")


def _extract_published_date_label(raw: object) -> str:
    """411 (2026-05-20): published_date を YYYY-MM-DD label に正規化。

    Tavily news topic は RFC 1123 (例: "Tue, 19 May 2026 13:30:00 GMT") を
    返すことが多いが、 ISO 8601 / unparseable も来うる。 parse 失敗時は
    「日付不明」 とし、 Gemma に古さの注意 hint を与える (hallucination 抑制)。
    """
    raw_str = str(raw or "").strip()
    if not raw_str:
        return "日付不明"
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw_str)
        return dt.strftime("%Y-%m-%d")
    except (TypeError, ValueError, IndexError):
        pass
    try:
        from datetime import datetime as _dt
        return _dt.fromisoformat(raw_str.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        pass
    # 最終 fallback: 先頭 10 文字が YYYY-MM-DD パターン
    if len(raw_str) >= 10 and raw_str[4] == "-" and raw_str[7] == "-":
        return raw_str[:10]
    return "日付不明"


def _extract_source_label(result: dict) -> str:
    """411 (2026-05-20): result から媒体名を抽出。

    Tavily は domain (例: "hochi.news") を返さない時があるが、 `url` から
    domain を取って media label に変換する。 unknown domain は 「不明媒体」。
    """
    url = str(result.get("url") or "").strip()
    if not url:
        return "不明媒体"
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return "不明媒体"
    label_map = {
        "giants.jp": "巨人公式",
        "npb.or.jp": "NPB公式",
        "hochi.news": "スポーツ報知",
        "sponichi.co.jp": "スポニチ",
        "nikkansports.com": "日刊スポーツ",
        "sanspo.com": "サンスポ",
        "daily.co.jp": "デイリースポーツ",
        "chunichi.co.jp": "中日スポーツ",
        "sports.yahoo.co.jp": "Yahoo!スポーツ",
    }
    for domain_key, label in label_map.items():
        if host == domain_key or host.endswith("." + domain_key):
            return label
    return host or "不明媒体"


def _format_tavily_context(results: list[dict], *, snippet_len: int = 300) -> str:
    """411 (2026-05-20): 各 result に `[YYYY-MM-DD] [媒体名] <タイトル> — <抜粋>` 形式で整形.

    user 仕様: Tavily の answer は使わず、 URL 本文・媒体名・日付を見る。
    Gemma に「いつの記事か」「どの媒体か」 を明示し、 古い snippet で現在形を
    生成しないよう context で hint。
    """
    lines = []
    for r in results:
        title = str(r.get("title") or "").strip()
        content = str(r.get("content") or "").strip()
        if not title and not content:
            continue
        date_label = _extract_published_date_label(r.get("published_date"))
        source_label = _extract_source_label(r)
        lines.append(
            f"- [{date_label}] [{source_label}] {title} — {content[:snippet_len]}"
        )
    return "\n".join(lines)


def build_gemma_branding_candidate(
    player_name: str,
    *,
    gemini_api_key: str,
    tavily_api_key: str,
    db_fact_line: str = "",
    max_tavily_results: int = 3,
    timeout_seconds: int = 30,
    model_id: str = _GEMMA_BRANDING_MODEL,
    temperature: float = 0.4,
    logger: Optional[_logging.Logger] = None,
    db_path: str = "",
    persona: Optional[str] = None,
    same_day_only: Optional[bool] = None,
    db_fact_streak_window: Optional[int] = None,
    post_type: Optional[str] = None,
    focused_players: Optional[list[str]] = None,
    fan_voice_snippet: str = "",
    starting_pitcher_today: str = "",
) -> Optional[Candidate]:
    """Tavily REST 検索 + Gemma 4 31B 生成で 1 件の Candidate を返す。

    silent skip 条件 (``None`` 返却):
    - player_name 不正 / 巨人 roster 不一致
    - API key 不足
    - Tavily 失敗 (factual ground 無し → hallucination 抑制のため生成しない)
    - Gemma 失敗 (rate limit / network 等)
    - 空生成 / spec 382 hard rule 違反 (validator drop)
    """
    log = logger or _logging.getLogger("x_post_branding_gen")
    player = str(player_name or "").strip()
    if not player or not gemini_api_key or not tavily_api_key:
        log.info("gemma_branding_skip reason=missing_input player=%r", player)
        return None
    if not _is_verified_full_giants_player_name(player):
        log.info("gemma_branding_skip reason=not_verified_giants_player player=%r", player)
        return None

    # 411 / 414 axis C9: persona 自動選択。 試合日 18-21時 = 缶詰、 他 = フーガ。
    # caller が persona kwarg で明示指定すれば自動選択を override。 同じく
    # same_day_only / db_fact_streak_window も persona に応じて自動 (缶詰=当日 only)。
    from datetime import datetime, timezone, timedelta
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    if persona is None:
        is_game_day = is_giants_game_day(now_jst, db_path) if db_path else False
        resolved_persona = select_branding_persona(now_jst, is_game_day)
    else:
        resolved_persona = persona
    # 414 axis C9: 缶詰 persona (試合中実況) は当日 only (古い snippet / 過去 streak を拾わない)
    if same_day_only is None:
        same_day_only = (resolved_persona == "kandume")
    if db_fact_streak_window is None:
        db_fact_streak_window = 0 if resolved_persona == "kandume" else 5

    # 1. Tavily 検索 (factual ground)
    query = f"巨人 {player} 最新"
    results = _tavily_search(
        query,
        tavily_api_key,
        max_results=max_tavily_results,
        timeout_seconds=timeout_seconds,
        same_day_only=same_day_only,
    )
    if not results:
        log.warning(
            "gemma_branding_skip reason=no_tavily_results query=%r player=%s persona=%s same_day_only=%s",
            query,
            player,
            resolved_persona,
            same_day_only,
        )
        return None
    # 414 axis C6: persona=fuuga (古い snippet 許容) でも 7 日超は strict drop。
    # 缶詰 (same_day_only=True) は既に当日 filter 経由なので no-op に近い。
    results = _recent_published_within_days(results, days=7)
    if not results:
        log.warning(
            "gemma_branding_skip reason=tavily_results_too_old query=%r player=%s",
            query,
            player,
        )
        return None
    context = _format_tavily_context(results)
    if not context:
        log.warning(
            "gemma_branding_skip reason=empty_tavily_context query=%r player=%s",
            query,
            player,
        )
        return None
    system_prompt = _build_system_prompt(
        now_jst_hour=now_jst.hour,
        today_jst=now_jst.strftime("%Y-%m-%d"),
        persona=resolved_persona,
    )
    # 414 axis A: 型自動選択。 caller が post_type kwarg で明示すれば override。
    if post_type is None:
        is_game_day_val = is_giants_game_day(now_jst, db_path) if db_path else False
        resolved_post_type = select_post_type(
            now_jst,
            is_game_day_val,
            has_db_fact=bool(db_fact_line),
            has_tavily_results=bool(results),
        )
    else:
        resolved_post_type = post_type
    post_type_guidance = _POST_TYPE_GUIDANCE.get(resolved_post_type, "")
    # 414 axis E: 試合前 (試合日 + 17時以前) のみ 7 テーマを prompt に注入
    pregame_section = ""
    if db_path and 5 <= now_jst.hour < 17:
        try:
            from src.analysis.pregame_themes import (
                build_pregame_themes,
                format_pregame_themes_for_prompt,
            )
            themes = build_pregame_themes(
                db_path,
                now_jst=now_jst,
                starting_pitcher_today=starting_pitcher_today,
                focused_players=focused_players,
                fan_voice_snippet=fan_voice_snippet,
            )
            pregame_section = format_pregame_themes_for_prompt(themes)
        except Exception as exc:  # noqa: BLE001 - silent fallback
            log.info("pregame_themes_skip reason=%r", exc)
    prompt_parts = [system_prompt]
    if post_type_guidance:
        prompt_parts.extend(["", post_type_guidance])
    if pregame_section:
        prompt_parts.extend(["", pregame_section])
    prompt_parts.extend([
        "",
        f"対象選手: {player}",
        "",
        f"DB 照合済み数字 (使ってよい数字): {db_fact_line or 'なし'}",
        "",
        "Tavily 検索結果 (context、 ここから不検証数字 / 引用 / 媒体名 / URL は使わない):",
        context,
        "",
        "上記情報を踏まえて、 独自の視点で X 投稿案を 1 件、 本文のみ書いてください。",
    ])
    prompt = "\n".join(prompt_parts)
    try:
        from google import genai
        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config={"temperature": temperature},
        )
        text = (getattr(response, "text", None) or "").strip()
    except Exception as exc:  # noqa: BLE001 - silent skip is the fault-tolerance contract
        log.warning(
            "gemma_branding_skip reason=gemini_error player=%s err=%r",
            player,
            exc,
        )
        return None

    text = _finalize_post_text(text)

    # 3. spec 382 hard rule + 414 axis D 炎上防止 validator
    if not _gemma_branding_safety_check(text):
        # 414 axis C7 + D: 構造化 drop log (どの pattern が hit したか + 軸名)
        matched_pattern: Optional[str] = None
        matched_axis: str = "C"  # default: forbidden patterns (axis C)
        for pattern in _GEMMA_BRANDING_FORBIDDEN_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_pattern = pattern.pattern
                matched_axis = "C"
                break
        if matched_pattern is None:
            # 軸 D: 炎上 patterns hit を確認
            inflammatory_match = _matched_inflammatory_pattern(text)
            if inflammatory_match:
                matched_pattern = inflammatory_match
                matched_axis = "D"
        log.warning(
            _json.dumps(
                {
                    "event": "gemma_branding_drop",
                    "reason": "safety_check_failed",
                    "axis": matched_axis,
                    "player": player,
                    "persona": resolved_persona,
                    "post_type": resolved_post_type,
                    "matched_pattern": matched_pattern,
                    "text_preview": text[:80],
                    "text_len": len(text),
                },
                ensure_ascii=False,
            )
        )
        return None

    # 414 axis C2: 数値 whitelist。 verified_text = db_fact_line + Tavily context。
    # 生成 text の数字で verified_text に literal 含まれない場合は drop。
    verified_text = " ".join(filter(None, [db_fact_line or "", context]))
    unverified = _extract_unverified_numbers(text, verified_text)
    if unverified:
        log.warning(
            _json.dumps(
                {
                    "event": "gemma_branding_drop",
                    "reason": "unverified_numbers",
                    "player": player,
                    "persona": resolved_persona,
                    "post_type": resolved_post_type,
                    "unverified_numbers": unverified[:10],
                    "text_preview": text[:80],
                },
                ensure_ascii=False,
            )
        )
        return None

    # 4. Candidate dataclass
    signature_hash = _hashlib.sha1(
        f"gemma_branding|{player}|{text[:80]}".encode("utf-8")
    ).hexdigest()[:16]
    draft_lines = [
        "【根拠: Gemma 4 + Tavily HTTP REST + 任意 DB 参照】",
        f"対象選手: {player}",
        f"検索 query: {query}",
        f"Tavily 結果数: {len(results)}",
        f"DB fact 注入: {'あり' if db_fact_line else 'なし'}",
        f"model: {model_id}",
        "",
        "【Tavily 検索結果 snippet】",
        context,
    ]
    if db_fact_line:
        draft_lines.extend(["", "【DB fact line】", db_fact_line])
    log.info(
        "gemma_branding_candidate_built player=%s tavily_results=%d text_len=%d",
        player,
        len(results),
        len(text),
    )
    return Candidate(
        title=f"Gemma 4 branding｜{player}",
        metric=_GEMMA_BRANDING_METRIC,
        period_label="LLM 生成",
        draft_text="\n".join(draft_lines),
        post_text=text,
        char_count=len(text),
        signature=f"gemma_branding|{signature_hash}|False|None",
        focus_player=player,
        source_material_type="gemma_branding",
    )
