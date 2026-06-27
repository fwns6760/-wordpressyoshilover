"""福祉エバーグリーン枠（新着ニュースが0件の便で「必ず1通」出すための常設ポスト）。

新着ニュースが取れない便（Google News が Cloud Run の IP から 429 で取れない等）でも
メールを欠かさないよう、外部取得に一切依存しない常設の当事者向けポストを作る。

- ペルソナ: IT特化型就労移行支援(#チームシャイニー)の部門長兼講師（Webマーケ/エンジニア歴20年）。
- 読み手: 発達障害・うつ等のある方の「ITで活躍したい」気持ち。ご家族。
- 当事者ファースト: ①あるある・共感 → ②そっと前向きな一言。技術解説や宣伝はしない。
- やわらかい『です・ます』。絵文字は1個まで（無くてよい）。署名・URL・ハッシュタグ・@は書かない。
- 引用元は無い（通常ポスト）。Xへの自動投稿はしない（メールのボタンを人が押す）。

`BaseballWelfarePost` を返り値の器として再利用する（text / quote_tweet_url=None /
source_note / is_ai）。compose 側は引用元なしの通常ポストとして扱う。
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request

from src.careland_baseball_welfare import BaseballWelfarePost

LOG = logging.getLogger(__name__)

# 常設アングル。seed（日時から算出）でローテーションし、1日5便でも被りにくくする。
# headline=1行目の【主題】 / body=共感→前向きの短い本文（テンプレ fallback 用）。
EVERGREEN_ANGLES: tuple[dict[str, str], ...] = (
    {
        "headline": "特性は、活かし方しだい",
        "body": "「みんなと同じやり方が、どうも合わない」と感じること、ありませんか。"
                "それは欠点ではなく、合う環境がまだ見つかっていないだけかもしれません。"
                "自分に合った役割と少しの工夫があれば、特性はちゃんと強みになります。",
    },
    {
        "headline": "休むのも、ちゃんとした計画",
        "body": "調子には波があって、いったん退いて立て直す時間も立派な戦略です。"
                "体調と付き合いながら働くときは、無理なく続ける工夫のほうが長く効きます。"
                "今日がんばれなくても、それで終わりではありません。",
    },
    {
        "headline": "小さな「できた」を数える",
        "body": "大きな成果より、今日できた小さなことを一つずつ数えてみてください。"
                "その積み重ねが、自信になり、次の一歩の力になります。"
                "就労の準備も、そうやって少しずつ進んでいきます。",
    },
    {
        "headline": "学び直しは、いつからでも",
        "body": "「今さら」と思う必要はありません。ITやデジタルのスキルは、"
                "年齢や経歴に関係なく、コツコツ続けた人のところに積み上がっていきます。"
                "在宅やリモートという働き方も、自分に合う場所を選ぶ武器になります。",
    },
    {
        "headline": "比べない、自分のペースで",
        "body": "まわりの速さと比べると、苦しくなってしまうことがあります。"
                "でも進むペースは人それぞれで、ゆっくりでも前に進んでいれば大丈夫です。"
                "あなたのペースで積み上げたものは、ちゃんと残ります。",
    },
    {
        "headline": "一人で抱えなくていい",
        "body": "「相談するほどでもないかな」と一人で抱えてしまうこと、ありませんか。"
                "迷ったときに少し誰かに話すだけで、見え方が変わることがあります。"
                "頼ることは弱さではなく、長く働き続けるための大事なスキルです。",
    },
    {
        "headline": "合う場所が見つかると、力が出る",
        "body": "新しい環境に飛び込むのは、誰でも不安なものです。"
                "最初は緊張しても、自分に合う場所で役割が見つかると、ちゃんと力を出せます。"
                "今うまくいかないのは、まだ場所が合っていないだけかもしれません。",
    },
    {
        "headline": "得意を、言葉にしてみる",
        "body": "自分の「これができる」を言葉にするのは、案外むずかしいものです。"
                "でも特性や得意を“これからの強み”として伝えられると、見てもらえる場所が広がります。"
                "うまく書けなくても、一緒に整理していけたらうれしいです。",
    },
)


def _pick_angle(seed: int) -> dict[str, str]:
    return EVERGREEN_ANGLES[seed % len(EVERGREEN_ANGLES)]


def _template_text(angle: dict[str, str]) -> str:
    """Gemini が使えない／落ちた時の固定文。"""
    return f"【{angle['headline']}】\n{angle['body']}"


def _build_prompt(angle: dict[str, str]) -> str:
    return (
        "あなたは「IT特化型の就労移行支援事業所（#チームシャイニー）」の部門長兼講師です。"
        "Webマーケ/エンジニア歴20年。発達障害・うつ病のある方の「ITで活躍したい」を応援しています。\n\n"
        f"# 今日のテーマ\n主題: {angle['headline']}\n伝えたいこと: {angle['body']}\n\n"
        "# 作るもの: 上のテーマをもとにした、あなたの一人称のオリジナルXポスト本文。\n"
        "# ルール\n"
        "- 1行目に【主題】を短く置いて改行、2行目から本文。全体100〜140字で簡潔に（長くても150字）。\n"
        "- 必ず『①当事者のあるある・共感 → ②そっと前向きな一言』の流れにする。\n"
        "- 当事者（発達障害・うつ病があり「ITで活躍したい」と考える方）やご家族への、温かく前向きな励ましにする。\n"
        "- 技術解説・宣伝・募集はしない。仕組みの説明や「○○とは」のような説明口調にしない。\n"
        "- 医療・診断・薬・障害年金の可否・法律の話は断定しない。煽らない。決まり文句で締めない。\n"
        "- やわらかい『です・ます』。絵文字は1個まで（無くてよい）。URL・ハッシュタグ・@メンションは書かない。\n"
        "# 出力\n本文のみを書く（前置きやJSONや見出しラベルは付けない）。"
    )


def _generate_ai_text(prompt: str, *, api_key: str, timeout: int) -> str | None:
    try:
        from src.gemini_model_policy import generate_content_url, select_gemini_model

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 512,
                "temperature": 0.7,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }).encode("utf-8")
        model = select_gemini_model()
        api_url = generate_content_url(api_key, model)
        req = urllib.request.Request(api_url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.load(res)
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text.strip("`").strip() or None
    except Exception as exc:  # noqa: BLE001 - 失敗は fallback
        LOG.warning("welfare_evergreen_ai_failed error=%s", type(exc).__name__)
        return None


def build_welfare_evergreen_post(
    *,
    seed: int = 0,
    api_key: str | None = None,
    timeout: int = 12,
) -> BaseballWelfarePost:
    """新着0件の便で「必ず1通」出す福祉エバーグリーンのポスト候補を作る。

    外部取得には依存しない（＝失敗しない）。Gemini が使えれば本文を生成し、
    使えない/落ちたら常設テンプレ文を使う。引用元なしの通常ポスト。
    """
    angle = _pick_angle(seed)
    key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
    text = _generate_ai_text(_build_prompt(angle), api_key=key, timeout=timeout) if key else None
    is_ai = bool(text)
    if not text:
        text = _template_text(angle)
    return BaseballWelfarePost(
        text=text.strip(),
        quote_tweet_url=None,
        quote_tweet_text=None,
        source_note="新着ニュースが無い便のため、当事者向けの常設ポストです",
        is_ai=is_ai,
    )


__all__ = [
    "EVERGREEN_ANGLES",
    "build_welfare_evergreen_post",
]
