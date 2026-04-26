# 124 published-cleanup-apply-runner

## meta

- number: 124
- alias: -
- owner: Claude Code(設計 + spec 起票)/ Codex A(後続実装、user 判断後)
- type: ops / post-publish cleanup runner / doc-first spec
- status: **READY**(spec 起票)/ live 適用は BLOCKED_USER
- priority: P1(108 audit land 後の自然な後続、105 ramp と独立)
- lane: A / Codex A
- created: 2026-04-26
- parent: 108(audit、commit `84b91ce`)/ PUB-004-B(cleanup contract、commit `f451f17`)

## 目的

108 audit で検出済の `cleanup_proposals` を **公開済 WP 記事に実適用**する runner spec。
PUB-004-B = **pre-publish** cleanup(publish 直前の draft cleanup)に対し、本 ticket = **post-publish** cleanup(既公開記事の事後修復)。

具体的には:
- 本日 publish 8 件(63405 / 63489 / 63335 / 63381 / 63307 / 63280 / 63278 / 63257)の `site_component_heavy` を post-hoc cleanup
- 既存公開全件の cleanup 候補を user 1 ワード判断後に live 適用
- 各適用は backup + 3-gate refuse + history 記録

## 前提

- 108 cleanup audit が land 済(`84b91ce`)= cleanup_proposals JSON 生成可能
- PUB-004-B detector(`heading_sentence_as_h3` / `dev_log_contamination` / `weird_heading_label` / `site_component_mixed_into_body`)= 本 runner で再利用
- WP REST `update_post_fields(post_id, content=cleaned_html)` 経路 = 既存 `src/wp_client.py`
- live 適用は **user 判断境界**(本 ticket spec 起票のみ、実装 fire は user 明示後)

## 不可触

- backend Python 主線(PUB-004-A/B / 108 audit)= 流用のみ、改変禁止
- WP plugin / front / build / logs
- `RUN_DRAFT_ONLY` flip
- Cloud Run env / scheduler / .env / secret
- automation / X / SNS POST
- baseballwordpress repo
- AdSense 関連(117 別 lane)
- `git add -A` / `git push`(Claude が後で push)

## 設計(後続実装の見取り図)

### 124-A: cleanup-apply-dry-run helper

#### scope
- 新規 module: `src/published_cleanup_apply.py`
- 新規 CLI: `src/tools/run_published_cleanup_apply.py`
- 新規 tests: `tests/test_published_cleanup_apply.py`

#### CLI
```
python3 -m src.tools.run_published_cleanup_apply \
  --input-from /tmp/published_cleanup_audit.json   # 108 output \
  --max-burst 3 \
  --backup-dir /home/fwns6/code/wordpressyoshilover/backups/wp_published_cleanup/ \
  --history-path /home/fwns6/code/wordpressyoshilover/logs/published_cleanup_history.jsonl \
  --format json|human \
  [--live]                  # 3-gate enable
  [--daily-cap-allow]       # 日 5 件 cap 許可
```

#### 3-gate refuse(PUB-004-B contract と同形)
1. `--live` 不在 → dry-run、proposed diff 表示のみ
2. `--max-burst <=3` 不在 or > 3 → refuse
3. `--daily-cap-allow` 不在 + 当日 cleanup 既 5 件以上 → refuse

#### per-post 適用 flow
1. preflight: post status = publish 確認
2. backup: `backups/wp_published_cleanup/YYYY-MM-DD/post_<post_id>_<UTCISO>.json`(content_pre 保存)
3. cleanup detector 再走(108 audit から差分なら skip)
4. cleanup 適用(タグ置換 / block 削除)
5. **post-cleanup 本文 check**(prose < 100 / title 主語消失 / source 表記消失 → refuse)
6. WP REST `update_post_fields(post_id, content=cleaned_html)`
7. postcheck: REST GET status=publish + content 反映確認
8. history 記録: `logs/published_cleanup_history.jsonl`(成功 / refuse 全 record)

#### history.jsonl format
```jsonl
{"post_id": ..., "ts": "<JST ISO>", "status": "applied|refused|skipped", "cleanup_types": [...], "backup_path": "...", "error": "...|null"}
```

### 124-B: cleanup-apply-cron-activation(PUB-004-C と並走判断)

- 124-A 安定運用 1〜2 日 + 失敗 0 件後、WSL cron 化
- 1 日数回(`0 7,13,20 * * *` 等)、burst cap 3 / daily cap 5
- crontab marker: `# 124-WSL-CRON-PUBLISHED-CLEANUP`
- 詳細 spec は別 ticket(本 ticket = 124-A spec 起票まで)

## acceptance(本 ticket、doc-first まで)

1. 108 audit 出力を input にする interface 仕様確定
2. 3-gate refuse + backup + post-cleanup check + history 記録 が PUB-004-B 同形
3. live 適用は **user 判断境界**(本 ticket scope = doc-first まで)
4. 124-A 実装の write_scope / acceptance / test_command 定義済
5. PUB-004-B(pre-publish)と 124(post-publish)の境界明確

## 後続実装条件

- 本 ticket 起票 + 102 board 反映 = doc-first 完了
- 124-A 実装 fire = user 1 ワード判断(`124-A go` 等)後
- 124-B cron 化 = 124-A 安定後 + user 別判断

## 関連 file

- `doc/108-existing-published-site-component-cleanup-audit.md`(audit 元)
- `doc/PUB-004-guarded-auto-publish-runner.md`(PUB-004-B = pre-publish cleanup contract、本 ticket は post-publish 版)
- `src/published_site_component_audit.py`(108 audit、本 ticket で input source)
- `src/guarded_publish_runner.py`(PUB-004-B、cleanup detector 既設)
- `src/wp_client.py`(`update_post_fields`、流用のみ非改変)
- `src/guarded_publish_evaluator.py`(PUB-004-A、import 可)

## stop 条件

- 108 audit 結果に異常(false-positive 過多)→ 124 fire 前に 108 retune 必要
- backup 失敗 → cleanup 適用しない
- post-cleanup check fail(prose 崩壊 / 主語消失 / source 消失)→ 当該 post skip
- WP REST update_post_fields 失敗 → 当該 post refuse + history 記録
- 既存公開 5 件超 / 1 cron tick → daily cap 超過 stop
