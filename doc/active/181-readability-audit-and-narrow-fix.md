# 181 readability audit & narrow fix(title 主語欠落 + 本文可読性)

## meta

- number: 181
- owner: Claude Code(設計 / 起票)/ Codex B(audit + 実装)
- type: dev / quality / readability
- status: **READY**(user Q2=auto、即 fire)
- priority: P0.5
- lane: B
- created: 2026-04-26

## 背景

user 観測(2026-04-26 evening):
- post 63668: title `が28日からの9連戦で1軍昇格へ`(冒頭「が」、主語「戸郷翔征が」が欠落)
- post 63375: title `選手「初出場初安打」 実戦で何を見せるか`(冒頭「選手」、本来 player 名)
- 共通: **title 先頭の主語(player 名)が脱落**
- 共通: 「読者が読みやすく」改善要

「もっと早く本文直していきたい」+「おかしかったらすぐ直す」mode。

## ゴール

1. 直近 publish 30-50 記事を audit、title / lead 段落の readability 問題 top 3 issue 特定
2. 各 issue に narrow fix(prompt / playbook / validator のいずれか)
3. 既存 pytest baseline(1409+)維持しつつ test 追加
4. fix 適用後の next publish で改善 verify(後日 user 観測)

## audit 観点(最低 5 軸)

- **title 主語欠落**(player 名 / 球団名 が冒頭欠落)
- **title 句切れ**(「、」「。」で title が中途切れ)
- **lead 抽象的すぎ**(具体名 / 数字 / 試合 ID なし冒頭 1 文)
- **本文 lead 主語不在**(冒頭から「が」「は」「で」始まり)
- **数字 / 固有名詞の重複**(同じ player / 数字が冒頭 2 段落で連発)

## 仕様(audit + narrow fix)

### Phase 1: audit(read-only)

- WP REST GET 直近 publish 50 記事(`status=publish`、`orderby=date desc`)
- 各記事 title + lead 第 1 段落 取得
- 上記 5 軸で issue 検出 + post_id list 化
- 結果 → `doc/active/181-deployment-notes.md` に集計表(issue 別件数 + 代表 post_id)

### Phase 2: narrow fix(top 3 issue 対象)

検出 top 3 issue ごとに narrow fix:

- **case A: title 主語欠落** → `src/title_body_nucleus_validator.py` or `src/rss_fetcher.py` の title 抽出 / truncation logic 修正(player 名先頭保持)
- **case B: title 句切れ** → 同上、適切な切り出し境界
- **case C: lead 抽象的** → `src/repair_playbook.py` に rule 追加(具体名 / 数字 / 試合 ID 必須)
- **case D / E: その他** → 必要なら同様 narrow fix

各 fix は **既存挙動を破壊しない**(既存 test 通る、新 test 追加で fix verify)。

### Phase 3: tests

- 新 test ケース(各 issue の fixture + 期待 fix output)
- pytest baseline 1409 維持(178 land 後の baseline で fire)

## 不可触

- WSL crontab 編集禁止
- WP write の new endpoint 追加禁止(本 ticket は code 修正のみ、live 検証は次 publish で観測)
- Cloud Run Job env / Cloud Scheduler 触らない(178 で land 済の現運用維持)
- 既存 src の挙動を **大幅変更**しない(narrow fix、minimum-diff)
- 165 / 168-179 / 156-167 / 176 / 177 / 178 で land 済の挙動を一切壊さない
- requirements*.txt 触らない
- automation.toml / .env / secrets / Cloud Run Job 触らない
- baseballwordpress repo
- 並走 task `b7sg11xi1`(178)が touching する file 触らない: `src/repair_fallback_controller.py` / `tests/test_repair_fallback_controller.py` / `doc/active/178-codex-primary-wp-write-enable.md`
- 並走 task touching file が増えたら同様 isolation

## acceptance

1. ✓ Phase 1 audit 結果(直近 50 publish 記事 + 5 軸 issue 検出 + 集計表)が `doc/active/181-deployment-notes.md` に記録
2. ✓ Phase 2 で top 3 issue 各々に narrow fix(src 1-3 file 修正 + tests)
3. ✓ pytest baseline 1409 + 新 tests pass
4. ✓ 既存挙動破壊なし(全既存 tests pass、pre-existing fail 0 維持)
5. ✓ WP write / Cloud Run deploy / push: 全て NO
6. ✓ commit + push なし(Claude が後で push)
7. ✓ 並走 178 と file 衝突なし

## Hard constraints

- 並走 task touching file 触らない
- `git add -A` 禁止、stage は変更 src + tests + `doc/active/181-deployment-notes.md` だけ明示
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest baseline 維持、pre-existing fail 0 維持
- 新 dependency 禁止
- minimum-diff、scope 拡大禁止

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3
# audit smoke (read-only)
python3 -c "
import sys; sys.path.insert(0, '.')
from src.wp_client import WPClient
c = WPClient()
posts = c.list_posts(status='publish', per_page=10, orderby='date', order='desc')
for p in posts[:5]:
    title = p.get('title',{}).get('rendered','')[:80]
    print(p.get('id'), '|', title)
"
```

## Commit

```bash
git add <変更 file 群を明示>
git status --short
git commit -m "181: readability audit + narrow fix top 3 issue (title 主語欠落 + lead 抽象的 + ...)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

- changed files
- pytest collect: 1409 → after
- audit 結果: 検出件数 / top 3 issue / 代表 post_id
- 各 narrow fix 内容 + tests
- 既存挙動破壊: なし verify
- WP write / Cloud Run deploy / push: 全て NO
- commit hash

## stop 条件

- audit で fix 不可能な巨大設計 issue 発覚 → 即停止 + 報告(別 ticket 化)
- 既存 src 大幅変更が必要 → 即停止 + 報告
- pytest baseline を割る → 即停止 + 報告
- 並走 178 と衝突 → 即停止 + 報告
