# 131 publish-notice notification (always-deliver + batch summary + alerts)

## meta

- number: 131
- alias: -
- owner: Claude Code(設計)/ Codex A(実装)
- type: ops / mail notification logic / alert add
- status: READY
- priority: **P0**(130 cap 100/日 反映で必須、即 fire)
- lane: A
- created: 2026-04-26
- policy lock: 2026-04-26(suppress しない、気づける通知へ)
- parent: 095-D / 088 / 130

## 目的

mail を **減らすことではなく、気づける通知にする**。
130 で daily cap 100 / burst cap 20 に変更 = 1 日最大 100 件 publish 想定。
通常通知は維持しつつ、burst 中の summary 追加 + 異常時の即時 alert を厚くする。

## 通知 layer

### Layer 1: per-post 通常通知(維持、変更なし)
- 既存挙動: 1 publish = 1 mail
- 全 publish で必ず配信、suppress しない
- subject: `[公開通知] Giants <title>`

### Layer 2: batch summary mail(新規追加)
- 1 cron tick 内で **10 本ごとに 1 通の summary mail** 追加
- 例: 1 tick で 20 件 publish = per-post 20 通 + summary 2 通(10 / 20 件目)= 計 22 通
- subject: `[公開バッチ summary] Giants N 件公開(<最初 title> 〜 <最後 title>)`
- body: 10 件分の title + canonical URL + 公開時刻一覧(各 1 行)
- 目的: per-post mail が紛れた時の「全体俯瞰」用

### Layer 3: 即時 alert mail(新規、burst 中の異常検知)
以下のいずれかで **即時 alert 1 通**(per-post 通常通知とは別経路):

| 異常 | alert subject | 検知元 |
|---|---|---|
| **Hard Stop hit** | `[ALERT] Giants Hard Stop hit: <reason>` | PUB-004-A evaluator が hard_stop 判定 |
| **publish 失敗** | `[ALERT] Giants publish failed: post_id=<id> reason=<...>` | PUB-004-B runner で WP REST update_post_status 5xx 等 |
| **postcheck 失敗** | `[ALERT] Giants postcheck failed: post_id=<id> http=<code>` | 公開後 public URL HTTP != 200 |

### Layer 4: emergency mail(致命的、即時 1 通)

| 異常 | emergency subject | 検知元 |
|---|---|---|
| **X / SNS 発火検知** | `[EMERGENCY] Giants X/SNS unintended post detected: post_id=<id>` | WP plugin / hook で auto-tweet が走った痕跡(meta 内 tweet_id 等) |

### Layer 5: duplicate 抑止(suppress)
- 同 post_id の重複通知のみ抑止(history.json dedup 既設、変更なし)
- 「**同じ通知が 2 度飛ぶ**」だけを防ぐ、それ以外は **送る**

## 重要制約

- 既存 `# 095-WSL-CRON-FALLBACK` cron line 変更なし(本 ticket = runner 拡張のみ)
- DOTENV-LOAD-088 既設 dotenv load 経路維持
- secret 表示禁止(MAIL_BRIDGE_* env 値非表示)
- backend Python narrow 改修(`src/publish_notice_email_sender.py` + `src/mail_delivery_bridge.py` 流用)
- WP write zero / X API zero / LLM zero
- 既存 publish-notice tests pass

## 不可触

- 095 cron line 自体(別便で必要時更新)
- backend 主線 src/wp_client.py / src/guarded_publish_evaluator.py / src/guarded_publish_runner.py(参照のみ、改変禁止)
- `RUN_DRAFT_ONLY` / Cloud Run env / `.env` 値
- automation / scheduler 改変
- baseballwordpress repo
- front / plugin / build
- requirements*.txt 改変
- `git add -A` / `git push`(Claude が後で push)

## 実装範囲

- 改修: `src/publish_notice_email_sender.py`
  - per-post layer は既存維持
  - batch summary layer 追加(10 件ごと閾値、env / flag で調整可)
  - alert layer 追加(Hard Stop / publish失敗 / postcheck失敗 検知 hook)
  - emergency layer 追加(X/SNS 発火検知 hook)
- 改修: `src/tools/run_publish_notice_email_dry_run.py`
  - flag 追加: `--summary-every N`(default 10)/ `--alert-on-hard-stop` / `--alert-on-failure` / `--emergency-on-sns-detected`
- 新規 tests: `tests/test_publish_notice_notification_layers.py`
- 既存 tests pass

## acceptance

1. per-post 通常通知 = 既存挙動維持(1 publish = 1 mail、suppress なし)
2. batch summary = 10 本ごとに 1 通追加(閾値調整可)
3. alert = Hard Stop / publish失敗 / postcheck失敗 で即時 1 通
4. emergency = X/SNS auto-post 検知で即時 1 通
5. duplicate = history dedup のみ抑止(既存挙動維持)
6. tests pass(per-post / summary / alert / emergency / duplicate-skip 各 case)
7. WP write zero / X API zero / secret 非表示 verify

## test_command

```
python3 -m pytest tests/test_publish_notice_notification_layers.py -v
python3 -m pytest tests/test_publish_notice_email_sender.py -v  # existing
python3 -m unittest discover -s tests 2>&1 | tail -3
python3 -m src.tools.run_publish_notice_email_dry_run --help
```

## next_action(本 ticket land 後)

1. 130 (Hard/Soft split) 実装と並走 = 130 land + 131 land 後に 105 再 dry-run autonomous
2. publishable 件数 > 0 想定 → live ramp 20 件 burst fire(PUB-004-B `--live --max-burst 20 --daily-cap-allow`)
3. cron tick で per-post 20 通 + summary 2 通 + alert N 通 自動配信
4. 24h 連続稼働で大量通知 / Gmail 着信 / spam filter / alert 動作 user 確認
5. 問題があれば cap 下げる or 通知 layer 調整

## 関連 file

- `doc/095-D-publish-notice-cron-live-verification.md`
- `doc/088-publish-notice-real-send-smoke-and-mail-gate-activation.md`
- `doc/130-pub004-hard-stop-vs-soft-cleanup-split.md`(parent、cap 変更元)
- `src/publish_notice_email_sender.py`(改修対象)
- `src/tools/run_publish_notice_email_dry_run.py`(改修対象)
- `src/mail_delivery_bridge.py`(参照のみ、改変禁止)
- `src/guarded_publish_runner.py`(alert hook 連携先)
- `src/guarded_publish_evaluator.py`(Hard Stop 判定連携元)
