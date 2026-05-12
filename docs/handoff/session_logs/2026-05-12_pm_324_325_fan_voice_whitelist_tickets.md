# 2026-05-12 PM — 324-QA / 325-QA fan voice whitelist RSS tickets 起票

## context

- user 質問: 「ふぁんの声の精度RSSで上がる方法あるの？」「値段は変わらない？」「XAPIはつかわないよ？」
- 結論: RSSHub に巨人ファン handle whitelist を追加する 2-stage ticket(source registration → picker integration)で precision 上昇可能、X API 不使用、追加コスト¥0 オーダー
- user 指示: 2 本同時起票(忘れ防止)

## 作業ログ

| HH:MM JST | event | ticket | task_id / commit_hash | next |
|---|---|---|---|---|
| 2026-05-12 PM | ticket 起票 commit | 324-QA + 325-QA | `a32f285` | handle curation 依頼便を user に投げる |

## 結果

- `doc/waiting/324-QA-fan-voice-whitelist-rss-source-registration.md` 新規(235 lines)
- `doc/waiting/325-QA-fan-voice-whitelist-rss-picker-integration.md` 新規
- 2 files changed, 235 insertions(+)
- branch: `draft-body-editor-reject-streak-no-fail`
- commit: `a32f285`
- src / config / test / env / scheduler / Cloud Run / X API / WP 本番 全て不可触

## scope 削減

- 当初計画では `doc/README.md` と `doc/active/assignments.md` への board 行追加も含めた 4 path commit を予定
- 直前 verify で 305-QA 関連の WIP(別作業者の未 commit 変更)が両 file に存在することを確認
- minimum-diff doctrine(`feedback_git_diff_cached_verify_strict` / CLAUDE.md §31-D)に従い、私の README + assignments 編集は revert、新規 ticket file 2 本だけ commit
- 305-QA WIP が landed した後の doc-only 後追い便で board 行追加予定

## blocked_by

- 324-QA: handle curation 待ち(user に 10〜20 件提示 → user yes/no)
- 325-QA: 324 landed + RSSHub 健全性観察 OK + user GO

## 次 action

- handle curation criteria を本 session で user に提示
- 305-QA WIP landed 後、別 doc-only 便で README + assignments 行追加
