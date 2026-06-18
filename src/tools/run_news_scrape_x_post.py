"""報知ニュース → scrape 型 X 投稿 → ワンタップ HTML メール を 1 本で流す runner。

usage:
    # 内蔵サンプル(小笠原入団)で HTML を書き出すだけ(送信しない)
    python3 -m src.tools.run_news_scrape_x_post --sample --out tmp_post_mail.html

    # facts JSON を渡して整形(報知 extractor 出力など)
    python3 -m src.tools.run_news_scrape_x_post --facts facts.json --out out.html

    # 実際に自分の Gmail へ 1 通送る(既定は dry-run。--send で実送信)
    python3 -m src.tools.run_news_scrape_x_post --sample --send --to fwns6760@gmail.com

facts JSON は任意の {ラベル: 値} dict。"コメント" キーに list[str] を入れると
引用として使われる。数字は出典そのままの文字列で入れること(モデルは整形のみ)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    """ローカル実行用に .env を読む(shell source 禁止 / python 経由で全キー)。

    既存の os.environ は上書きしない(shell 指定を優先)。"""
    import os
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
        return
    except Exception:
        pass
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = val.strip().strip('"').strip("'")


_load_env()

from src import news_scrape_x_post as nsx  # noqa: E402
from src import mail_delivery_bridge as mdb  # noqa: E402

# 内蔵サンプル(小笠原慎之介 入団。数字・引用は出典そのまま)
SAMPLE_FACTS = {
    "選手": "小笠原慎之介",
    "球団": "読売ジャイアンツ(巨人)",
    "会見": "2026年6月18日・東京ドーム",
    "背番号": "98",
    "投打": "左投左打",
    "中日通算9年": "161登板 46勝65敗 防御率3.62 757奪三振",
    "自己最高2022": "10勝8敗 防御率2.76",
    "MLBナショナルズ2025": "23登板 1勝1敗 防御率6.98",
    "経歴": "2015年中日ドラフト1位 → 中日9年 → 2025年ナショナルズ → 2026年6月 巨人",
    "コメント": [
        "(背番号98について)一度は大きな番号をつけてやってみよう。自分の中でもチャレンジ。僕の中でも特別な番号",
        "米国で学んだ変化球主体の投球をミックスして新天地での活躍を誓った",
    ],
    "出典": "入団会見(2026/6/18 東京ドーム) / NPB公式成績",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--sample", action="store_true", help="内蔵サンプル facts を使う")
    src.add_argument("--facts", help="facts JSON のパス")
    ap.add_argument("--article", help="記事本文 txt。「」発言を抽出して facts のコメントに合流")
    ap.add_argument("--label", default="X投稿 下書き(scrape型)")
    ap.add_argument("--quote-url", default=None, help="引用RT 用の元ツイート URL(任意)")
    ap.add_argument("--model", default=nsx.DEFAULT_MODEL)
    ap.add_argument("--out", default="tmp_post_mail.html", help="HTML 書き出し先")
    ap.add_argument("--send", action="store_true", help="実際にメール送信(既定は dry-run)")
    ap.add_argument("--to", default="fwns6760@gmail.com")
    args = ap.parse_args(argv)

    # facts は dict(単発) または list(複数まとめ)。list の各要素は
    # facts dict、または {"label","facts","quote_url"} の spec。
    if args.sample:
        raw = SAMPLE_FACTS
    else:
        raw = json.loads(Path(args.facts).read_text(encoding="utf-8"))

    if isinstance(raw, list):
        specs = []
        for item in raw:
            if isinstance(item, dict) and "facts" in item:
                specs.append((item.get("label", args.label), item["facts"], item.get("quote_url")))
            else:
                specs.append((args.label, item, None))
    else:
        specs = [(args.label, raw, args.quote_url)]

    article_quotes = []
    if args.article:
        article_quotes = nsx.extract_quotes_from_text(Path(args.article).read_text(encoding="utf-8"))

    cards = []
    drafts_text = []
    for label, facts, quote_url in specs:
        facts = dict(facts)
        if article_quotes:
            merged = list(facts.get("コメント", [])) + article_quotes
            facts["コメント"] = list(dict.fromkeys(merged))
        draft = nsx.format_scrape_post(facts, model=args.model)
        print(f"=== [{label}] draft ({len(draft)}/{nsx.X_CHAR_LIMIT}) ===\n{draft}\n")
        cards.append(nsx.build_post_card(draft, label=label, quote_url=quote_url))
        drafts_text.append(f"【{label}】\n{draft}")

    html = nsx.build_cards_email_html(cards)  # 1 枚でも複数でも同じ外枠で包む
    out_path = Path(args.out)
    out_path.write_text(html, encoding="utf-8")
    print(f"[html] wrote {out_path.resolve()} ({len(cards)} card(s))")

    subject = f"🌙 {args.label}" + (f"(他{len(cards)-1}件)" if len(cards) > 1 else "")
    request = mdb.MailRequest(
        to=[args.to],
        subject=subject,
        text_body="\n\n".join(drafts_text),
        html_body=html,
    )
    result = mdb.send(request, dry_run=not args.send)
    print(f"[mail] status={result.status} reason={result.reason} to={args.to} "
          f"({'LIVE SEND' if args.send else 'dry-run'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
