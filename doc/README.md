# doc/ — チケット一覧

AGENTS.md の機能をチケットに分割したもの。
実装順序に番号を振ってある。**番号順に進める。飛ばさない。**

TODOの状態：`【】` 未着手 → `【×】` 完了

---

## チケット一覧

| # | ファイル | 内容 | 担当 | 依存 |
|---|---------|------|------|------|
| 001 | [001-project-foundation.md](001-project-foundation.md) | プロジェクト共通基盤（ディレクトリ・設定ファイル） | Claude Code | なし |
| 002 | [002-swell-category-setup.md](002-swell-category-setup.md) | フェーズ① SWELL＋カテゴリ固定 | 手動 | なし |
| 003 | [003-wp-client.md](003-wp-client.md) | フェーズ② wp_client.py（共通WPクライアント） | Claude Code | 001, 002 |
| 004 | [004-wp-draft-creator.md](004-wp-draft-creator.md) | フェーズ② wp_draft_creator.py（下書き自動生成） | Claude Code | 001, 003 |
| 005 | [005-rss-fetcher.md](005-rss-fetcher.md) | フェーズ③ rss_fetcher.py（RSS取得＋自動分類） | Claude Code | 001, 003, 004 |
| 006 | [006-x-post-generator.md](006-x-post-generator.md) | フェーズ④ x_post_generator.py（X文案生成） | Claude Code | 001, 003 |
| 007 | [007-x-api-client.md](007-x-api-client.md) | フェーズ⑤ x_api_client.py（X API連携） | Claude Code | 001〜006すべて |
| 008 | [008-deploy-xserver.md](008-deploy-xserver.md) | エックスサーバーデプロイ・運用開始 | 手動 | 001〜006 |
| 009 | [009-top-design-swell.md](009-top-design-swell.md) | TOPページデザイン SWELL実装 | 手動+Claude Code | 002 |

---

## TODOの完了マーク方法

ファイルをエディタで開いて `【】` を `【×】` に書き換える。

```bash
# 例：003のTODOをひとつ完了にする
sed -i 's/【】`src\/wp_client.py` を作成/【×】`src\/wp_client.py` を作成/' doc/003-wp-client.md
```

## 各チケットの未完了TODOを確認

```bash
grep '【】' doc/001-project-foundation.md
grep '【】' doc/003-wp-client.md
# 全チケット一括
grep -rn '【】' doc/
```

## 全体の進捗確認

```bash
for f in doc/0*.md; do
  total=$(grep -c '【】\|【×】' "$f" 2>/dev/null || echo 0)
  done=$(grep -c '【×】' "$f" 2>/dev/null || echo 0)
  echo "$(basename $f): $done / $total 完了"
done
```
