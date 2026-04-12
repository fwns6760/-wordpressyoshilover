---
name: yoshilover フェーズ①進捗
description: yoshilover.com のフェーズ①実装状況・ブロッカー・次のアクション
type: project
---

## 作業ログ（2026-04-12）

### 完了済み ✅

| 内容 | 詳細 |
|------|------|
| カテゴリ8種作成 | ID 663〜670（試合速報・選手情報・首脳陣・ドラフト育成・OB解説者・補強移籍・球団情報・コラム） |
| categories.json更新 | config/categories.jsonにID記録済み |
| フロントページ設定 | show_on_front=posts、表示件数15件 |
| カテゴリナビメニュー | 「カテゴリナビ」作成・グローバルナビ(header_menu)に割り当て済み |
| サイドバーウィジェット | sidebar-1にXバナー・カテゴリ・人気記事・FAMILY STORIES・アーカイブの5種設置済み |
| 追加CSS適用 | wp_update_custom_css_post()でswell_child用CSS適用済み（Oswald・カテゴリドット・記事一覧・サイドバー等） |
| FTP接続確立 | claudecode@yoshilover.com / yoshilover.com で接続可能 |
| WP認証確立 | user / Hs4X TczM i0yq 4Z8l npaq X3j7（.env更新済み） |

### 未完了 ⚠️

| 内容 | 状況 | 対処法 |
|------|------|--------|
| SWELLカラー設定 | まだ旧カラー（#04384c青系）のまま | 下記「明日やること」参照 |
| 記事一覧リスト型 | カスタマイザーで手動設定が必要 | カスタマイズ → トップページ → リスト |
| ヘッダー背景 #1A1A1A | カスタマイザーで手動設定が必要 | カスタマイズ → ヘッダー |

### サーバーに残っているプラグイン（要対処）

- **yoshilover-debug.php** → プラグイン有効化後、REST APIで調査してから削除
- **yoshilover-colors.php** → 色が変わらなかったため調査中

---

## 明日やること（優先順）

### 1. SWELLカラーキー特定（デバッグプラグイン）

WP管理画面でプラグイン有効化後：
```
python3 -c "
import requests, json
r = requests.get('https://yoshilover.com/wp-json/yoshilover/v1/debug')
data = r.json()
print('theme_mods keys:', list(data['theme_mods'].keys())[:20])
for opt in data['swell_options']:
    print(opt)
"
```

→ SWELLの正しいカラーオプションキーを特定して再設定

### 2. カラー設定が難しければ手動でカスタマイザー

`https://yoshilover.com/wp-admin/customize.php`
- サイト全体設定 → メインカラー: `#F5811F`
- テキストカラー: `#333333`
- リンクカラー: `#003DA5`
- 背景色: `#F5F5F0`
- ヘッダー → 背景色: `#1A1A1A`
- トップページ → 記事一覧 → リスト型

### 3. カラー確認後、モックアップと見比べる

ブラウザで開くHTMLモックアップ:
`/home/fwns6/code/wordpressyoshilover/yoshilover-top-mockup.html`

---

## ファイル一覧

| ファイル | 用途 |
|---------|------|
| src/setup_phase1.py | フェーズ①自動セットアップ（認証チェック付き） |
| src/custom.css | 追加CSS（212行）手動貼り付け用バックアップ |
| src/yoshilover-colors.php | SWELLカラー設定プラグイン（現在サーバーに残存） |
| src/yoshilover-debug.php | SWELLオプション調査プラグイン（現在サーバーに残存） |
| yoshilover-top-mockup.html | 完成デザインのHTMLプレビュー |
| config/categories.json | カテゴリ名→WP ID対応表 |

## 認証情報（.envに記録済み）

- WP_URL: https://yoshilover.com
- WP_USER: user
- WP_APP_PASSWORD: Hs4X TczM i0yq 4Z8l npaq X3j7（ClaudeCodeで発行）
- FTP: claudecode@yoshilover.com / sebata1413 / yoshilover.com
