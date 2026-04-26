# 176 share-buttons-twitter-facebook-empty(front bug、share row 左 2 buttons 空白)

## meta

- number: 176
- owner: Claude Code(設計 / 起票)/ Codex(実装 + 調査、push しない、Claude が push)
- type: bug fix / front / SWELL theme
- status: **READY**(即 fire 可)
- priority: P1(共有導線、X 拡散影響)
- lane: B(front quality)
- created: 2026-04-26
- parent: 062 / 063-V* series(front 整理)/ 既存 SWELL share button 設定

## 背景

user 報告 + screenshot(`C:\Users\fwns6\OneDrive\Pictures\Screenshots\スクリーンショット 2026-04-26 183204.png`):

記事末尾の SHARE row、**左 2 buttons が空白**(白背景、アイコン / label 無し)、その右は 正常表示:
- ?(空白)
- ?(空白)
- 赤 = Pocket(♡ icon)
- 緑 = LINE(LINE icon)
- 橙 = Copy URL(clipboard icon)

順序的に左 2 つは **Twitter(X)+ Facebook** の share button が空表示になってる。

## 推定原因

`src/custom.css` line 2178-2197 で share button styling:
```css
.c-shareBtns__item.-twitter .c-shareBtns__btn,
.c-shareBtns__item.-x .c-shareBtns__btn {
  background: var(--black) !important;
}
.c-shareBtns__item.-facebook .c-shareBtns__btn {
  background: #1877F2 !important;
}
```

- 前提として `.c-shareBtns__item.-twitter` / `.-x` / `.-facebook` の class が適用されること
- 表示が **白(default)** = 上記 class が当たってない可能性
- SWELL theme update で class 名変更?(例: `.-twitter` → `.-tw` / `.-x-twitter`)
- もしくは button container は出てるが内部 icon SVG / label が空(SWELL 設定で disable?)

## ゴール

share row の Twitter(X)+ Facebook buttons を **正常に icon + 背景色付きで表示**する。

## 仕様(調査 + fix)

### Phase 1: 調査(read-only)

1. live サイト の share row HTML を `curl https://yoshilover.com/?p=63663` から取得
2. share row の `<ul class="c-shareBtns__list">` 配下を grep
3. 各 button の class を抽出(例: `.c-shareBtns__item.-x` or `.-twitter` or `.-facebook` or別名?)
4. icon が `<svg>` / `<i class="...">` どちらで rendered されてるか
5. SWELL theme version 確認(可能なら)

### Phase 2: fix(調査結果に応じて narrow fix)

**case A: class 名が `.-x` / `.-facebook` 以外(例 `.-tw`)**
- `src/custom.css` の該当 selector を実 class 名に追加 / 訂正

**case B: icon 要素が空(`<i>` 中身なし)**
- `src/yoshilover-063-frontend.php` で SWELL filter hook で icon SVG を補完
- もしくは `src/custom.css` で `::before` content で icon font 表示

**case C: SWELL admin 設定で Twitter / Facebook share が disable**
- user op(WP admin で enable)→ Codex は code 触らず stop

**case D: SWELL theme update が原因**
- SWELL 設定 reset or theme child override で対応

### 不可触

- WSL crontab / cron 時刻
- Cloud Run / GCP infra
- src/ 以外の WordPress 本体ファイル(theme child のみ操作)
- automation / scheduler / .env / secrets
- baseballwordpress repo
- WP admin 設定変更(case C のとき user 判断)
- 既存 SWELL theme 本体ファイル(child override / custom.css / 自作 plugin のみ)
- 並走 task `b3ngiu1an`(160 PUB-004-C GCP migration)が touching する file 触らない: `Dockerfile.guarded_publish` / `cloudbuild_guarded_publish.yaml` / `bin/guarded_publish_entrypoint.sh` / `doc/active/160-deployment-notes.md`

## acceptance

1. live サイト share row Twitter(X)+ Facebook button が **icon + 背景色(black + #1877F2)で表示**
2. CSS / PHP 修正後に live で curl 確認
3. 1-2 記事(63663 / 63668 等)で smoke verify
4. 既存正常 button(Pocket / LINE / Copy)の表示は破壊しない
5. WP admin 設定変更が必要な場合は user op として doc 化、Codex は code 触らず stop

## Hard constraints

- 並走 task `b3ngiu1an`(160)が touching する file 触らない
- `git add -A` 禁止、stage は **`src/custom.css` + `src/yoshilover-063-frontend.php`(必要な場合のみ)+ `doc/active/176-deployment-notes.md`** だけ明示
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest 影響なし(front file のみ)
- WP admin 設定変更禁止(case C 該当なら escalate)
- live deploy / WP file 直編集 禁止(repo の src/ 経由のみ、deploy は別 ticket)
- 165 / 168-173 / 156-167 で land 済の挙動を一切壊さない

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
# live HTML 取得 + share row grep
curl -s "https://yoshilover.com/?p=63663" | grep -A2 "c-shareBtns__item" | head -40
# CSS 修正後の検証は user op(browser で目視 + screenshot)
```

## Commit

```bash
git add src/custom.css src/yoshilover-063-frontend.php doc/active/176-deployment-notes.md
# 触らない file は除外
git status --short
git commit -m "176: share buttons Twitter/Facebook 空白 fix (class 名 訂正 or icon SVG 補完、live smoke verify)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

```
- changed files: <list>
- 推定原因: case A / B / C / D
- 修正内容: <CSS selector 追加 / icon SVG 補完 / その他>
- live smoke 1 記事: <URL>
- live smoke 2 記事(可能なら): <URL>
- 既存正常 button(Pocket / LINE / Copy)未変更 verify: yes
- WP admin 設定変更必要: yes/no(yes なら user op として doc 化)
- live deploy / push: 全て NO
- commit hash: <hash>
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- WP admin 設定変更が必要(case C)→ 即停止 + 報告(user op)
- SWELL theme 本体ファイル改変が必要 → 即停止 + 報告(別 ticket、theme update / fork 検討)
- live curl が WP REST から不正 response → 別 ticket
- 並走 task scope と衝突 → 即停止 + 報告
