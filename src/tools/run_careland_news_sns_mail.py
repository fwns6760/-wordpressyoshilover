"""CARE LAND 発達障害・福祉ニュース版 候補メールの Cloud Run Job エントリ。

finance_news_sns と同方式:
  - 公的発表/福祉メディアの公開ソースを取得
  - AIで価値判定 (x_article / x_only / weekly / hold / discard)
  - x_article は WordPress 下書き(draft)を作成（自動公開はしない）
  - 本文同梱の確認メールを Gmail で送信（承認ボタン付き）
  - SNS への自動投稿はしない / WordPress の自動公開はしない

ローカル確認:
  python3 -m src.tools.run_careland_news_sns_mail --dry-run --print-body
  python3 -m src.tools.run_careland_news_sns_mail --dry-run --print-body --no-judgment
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
import logging
import os
from pathlib import Path
import sys
from typing import Sequence
from zoneinfo import ZoneInfo

from src import mail_delivery_bridge as bridge
from src.tools import careland_news_sns_candidates as cnc
from src.careland_baseball_welfare import build_baseball_welfare_post
from src.careland_welfare_evergreen import build_welfare_evergreen_post

LOG = logging.getLogger("careland_news_sns_mail")
JST = ZoneInfo("Asia/Tokyo")
DEFAULT_SOURCES = Path(__file__).resolve().parents[2] / "config" / "careland_news_sources.example.json"


def _configure_logging() -> None:
    level_name = (os.environ.get("LOG_LEVEL") or "INFO").upper()
    logging.basicConfig(level=getattr(logging, level_name, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")


DEFAULT_MAIL_TO = "y.sebata@shiny-lab.org"


def _resolve_recipients(override: str | None) -> list[str]:
    raw = (override or os.environ.get("CARELAND_NEWS_MAIL_TO")
           or os.environ.get("MAIL_BRIDGE_TO") or DEFAULT_MAIL_TO)
    return [p.strip() for p in raw.split(",") if p.strip()]


def _resolve_wp_admin_base(override: str | None) -> str | None:
    return (override or os.environ.get("CARELAND_WP_ADMIN_BASE")
            or os.environ.get("WP_URL") or "https://careland.org")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CARE LAND 福祉ニュース候補メール。")
    p.add_argument("--dry-run", action="store_true", help="メールを送らない")
    p.add_argument("--to", default=None, help="送信先 (カンマ区切り)")
    p.add_argument("--sources", default=os.environ.get("CARELAND_NEWS_SOURCES_FILE") or str(DEFAULT_SOURCES))
    p.add_argument("--send-empty", action="store_true", help="候補0件でも送る")
    p.add_argument("--print-body", action="store_true", help="本文を表示")
    p.add_argument("--no-judgment", action="store_true", help="AI判定を使わずfallbackのみ")
    p.add_argument("--no-create-drafts", action="store_true",
                   help="x_article 候補の WordPress 下書きを作成しない（既定: 作成する）")
    p.add_argument("--wp-admin-base", default=None,
                   help="承認ボタンのリンク先 WordPress サイトURL（既定: WP_URL / careland.org）")
    p.add_argument("--max-candidates", type=int, default=int(os.environ.get("CARELAND_NEWS_MAX_CANDIDATES", "8")))
    p.add_argument("--max-items-per-source", type=int, default=int(os.environ.get("CARELAND_NEWS_MAX_ITEMS_PER_SOURCE", "20")))
    p.add_argument("--timeout-seconds", type=int, default=int(os.environ.get("CARELAND_NEWS_TIMEOUT_SECONDS", "6")))
    p.add_argument("--minimum-score", type=int, default=None)
    p.add_argument("--ledger-path", default=os.environ.get("CARELAND_NEWS_LEDGER_PATH"))
    p.add_argument("--ledger-gcs-uri", default=os.environ.get("CARELAND_NEWS_LEDGER_GCS_URI"))
    p.add_argument("--no-baseball", action="store_true",
                   default=bool(os.environ.get("CARELAND_NEWS_NO_BASEBALL")),
                   help="新着0件の便で @yoshilover6760 の野球ツイ→福祉の引用ポストを使わない"
                        "（既定: 候補0なら野球→福祉を優先、取れなければエバーグリーン）")
    p.add_argument("--no-evergreen", action="store_true",
                   default=bool(os.environ.get("CARELAND_NEWS_NO_EVERGREEN")),
                   help="新着0件の便で福祉エバーグリーンの常設ポストにも degrade しない"
                        "（既定: 野球が取れなければエバーグリーンで必ず1通送る）")
    return p.parse_args(argv)


def _create_drafts(candidates, *, now, config):
    """x_article 候補だけ WP draft を作る。status は draft 固定（自動公開しない）。"""
    from src.wp_client import WPClient
    from src.careland_news_article import build_article_draft

    wp_cfg = config.get("wordpress", {})
    breaking_id = int(wp_cfg.get("breaking_category_id", 55))
    category_map = {k: int(v) for k, v in (wp_cfg.get("category_map") or {}).items()}
    default_index = bool(wp_cfg.get("default_index", False))

    wp = WPClient()
    out = []
    for cand in candidates:
        if cand.decision != "x_article":
            out.append(cand)
            continue
        slug = f"careland-news-{now.strftime('%Y%m%d-%H%M%S')}-{cand.dedupe_key[:8]}"
        draft = build_article_draft(
            verdict=cand.verdict, title=cand.title, summary=cand.summary,
            source_name=cand.source_name, url=cand.url, lane=cand.post_lane,
            lane_label=cand.lane_label, breaking_id=breaking_id, category_map=category_map,
            default_index=default_index, slug_hint=slug,
            body_excerpt=cand.body_excerpt, hero_image_url=cand.hero_image_url,
        )
        # 元記事の og:image をアイキャッチ(featured)に取り込む。失敗しても記事は出す。
        featured_media = None
        if cand.hero_image_url:
            try:
                featured_media = int(wp.upload_image_from_url(cand.hero_image_url, source_url=cand.url)) or None
            except Exception as exc:  # noqa: BLE001
                LOG.warning("careland_eyecatch_upload_failed url=%s error=%s", cand.url, type(exc).__name__)
        try:
            post_id = wp.create_post(
                draft.title, draft.content, categories=list(draft.category_ids),
                status="draft", source_url=cand.url, featured_media=featured_media,
                caller="careland_news.run", source_lane="careland_news",
            )
            out.append(replace(cand, post_id=int(post_id), want_index=draft.want_index))
            LOG.info("careland_draft_created post_id=%s index=%s title=%s", post_id, draft.want_index, draft.title)
        except Exception as exc:  # noqa: BLE001 - 1件の失敗で全体を止めない
            LOG.warning("careland_draft_failed url=%s error=%s", cand.url, type(exc).__name__)
            out.append(cand)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    _configure_logging()
    args = _parse_args(argv)
    recipients = _resolve_recipients(args.to)
    if not recipients and not args.dry_run:
        LOG.error("No recipients (set CARELAND_NEWS_MAIL_TO or MAIL_BRIDGE_TO). Abort.")
        return 2
    if not recipients:
        recipients = ["dry-run@example.test"]

    now = datetime.now(JST)
    create_drafts = not args.no_create_drafts
    LOG.info("careland-news-sns fire @ %s JST dry=%s sources=%s judgment=%s drafts=%s",
             now.strftime("%Y-%m-%d %H:%M"), args.dry_run, args.sources,
             not args.no_judgment, create_drafts)

    result = cnc.build_candidates(
        source_path=args.sources, now=now,
        timeout_seconds=max(1, args.timeout_seconds),
        max_items_per_source=max(1, args.max_items_per_source),
        max_candidates=max(1, args.max_candidates),
        minimum_score=args.minimum_score,
        ledger_path=args.ledger_path, gcs_ledger_uri=args.ledger_gcs_uri,
        run_judgment=not args.no_judgment,
    )
    candidates = result.candidates
    decisions = {}
    for c in candidates:
        decisions[c.decision] = decisions.get(c.decision, 0) + 1
    LOG.info("careland_result candidates=%d decisions=%s loaded=%d raw=%d scored=%d deduped=%d skipped=%s",
             len(candidates), decisions, result.stats.loaded_sources, result.stats.raw_items,
             result.stats.scored_items, result.stats.deduped_items, result.stats.skipped_sources)

    # ---- 新着0件の便だけ「必ず1通」出す保険（新着がある便は増やさない＝送りすぎ防止）----
    # 優先: @yoshilover6760(巨人アカ) の最新ツイを福祉観点に翻訳した「引用ポスト」。
    #       元ツイが拾える便はこれを使う（野球→就労・特性を強み・学び直しに翻訳、@メンションなし）。
    # degrade: 元ツイが拾えない（nitter不通/Cloud RunでブロックされたDC IP等）便は、外部取得に
    #          依存しない福祉エバーグリーン（固定アングル）に切り替える。これで0件便でも必ず1通飛ぶ。
    baseball_post = None
    evergreen_post = None
    if not candidates and not args.send_empty:
        if not args.no_baseball:
            try:
                bp = build_baseball_welfare_post(timeout=max(8, args.timeout_seconds))
                if bp.quote_tweet_url:  # 実ツイが取れた時だけ採用（取れなければ evergreen へ）
                    baseball_post = bp
                    LOG.info("baseball_welfare_used quote=%s is_ai=%s",
                             bp.quote_tweet_url, bp.is_ai)
                else:
                    LOG.info("baseball_welfare_no_tweet (degrade to evergreen)")
            except Exception as exc:  # noqa: BLE001 - 野球枠の失敗で本体メールを止めない
                LOG.warning("baseball_post_build_failed error=%s", type(exc).__name__)
        if baseball_post is None and not args.no_evergreen:
            # 1日5便で被らないよう、日付＋便（時刻）で seed をローテーションする。
            seed = now.timetuple().tm_yday * 5 + now.hour
            try:
                evergreen_post = build_welfare_evergreen_post(
                    seed=seed, timeout=max(12, args.timeout_seconds))
                LOG.info("welfare_evergreen_used seed=%s is_ai=%s", seed, evergreen_post.is_ai)
            except Exception as exc:  # noqa: BLE001 - 常設枠の失敗で落とさない
                LOG.warning("welfare_evergreen_build_failed error=%s", type(exc).__name__)

    # 候補も保険も無いときだけ送らない（通常は野球→福祉 か エバーグリーンで必ず1通になる）。
    if (not candidates and not args.send_empty
            and baseball_post is None and evergreen_post is None):
        LOG.info("candidate count is 0 and no fallback post; skip mail")
        return 0

    if create_drafts and not args.dry_run:
        _sources, config = cnc.fnc.load_sources(args.sources)
        candidates = _create_drafts(candidates, now=now, config=config)

    wp_admin_base = _resolve_wp_admin_base(args.wp_admin_base)
    # yoshilover 同仕様: 候補ごとに 1 通（種別別カード）を送る。バッチ1通は廃止。
    share_bucket, share_fetcher_base, share_enabled = cnc.cshare.resolve_share_x_config()
    run_id = now.strftime("%Y%m%d-%H%M%S")

    mails: list[tuple[str, str, str, list]] = []
    for i, cand in enumerate(candidates, 1):
        mails.append(cnc.compose_candidate_mail(
            cand, now=now, idx=i, wp_admin_base=wp_admin_base,
            fetcher_base=share_fetcher_base, share_enabled=share_enabled,
            share_bucket=share_bucket, run_id=run_id,
        ))
    if baseball_post is not None:
        mails.append(cnc.compose_baseball_mail(baseball_post, now=now))
    if evergreen_post is not None:
        mails.append(cnc.compose_evergreen_mail(evergreen_post, now=now))

    sender = os.environ.get("MAIL_BRIDGE_FROM") or os.environ.get("NOTIFY_FROM")
    reply_to = os.environ.get("MAIL_BRIDGE_REPLY_TO")
    sent_ok = 0
    for subject, text_body, html_body, inline_images in mails:
        if args.print_body or args.dry_run:
            print(f"--- {subject} ---")
            print(text_body[:2000])
        request = bridge.MailRequest(
            to=recipients, subject=subject, text_body=text_body, html_body=html_body,
            sender=sender, reply_to=reply_to, inline_images=inline_images,
            metadata={"lane": "careland-news-sns"},
        )
        send_result = bridge.send(request, dry_run=args.dry_run)
        LOG.info("careland-news-sns mail result: subject=%s status=%s reason=%s refused=%s",
                 subject, send_result.status, send_result.reason, send_result.refused_recipients)
        if send_result.status in {"sent", "dry_run"}:
            sent_ok += 1
    if sent_ok == 0 and mails:
        return 4
    if sent_ok > 0 and not args.dry_run and candidates:
        cnc.fnc.append_ledger(
            [cnc.fnc.FinanceCandidate(
                source_id=c.source_id, source_name=c.source_name, market="",
                post_lane=c.post_lane, title=c.title, url=c.url, score=c.score,
                priority=c.priority, summary=c.summary,
            ) for c in candidates],
            now=now,
            ledger_path=args.ledger_path or os.environ.get("CARELAND_NEWS_LEDGER_PATH", "logs/careland_news_ledger.jsonl"),
            gcs_uri=args.ledger_gcs_uri or os.environ.get("CARELAND_NEWS_LEDGER_GCS_URI"),
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
