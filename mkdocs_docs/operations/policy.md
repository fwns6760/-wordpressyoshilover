# :material-account-group: 運用ルール

## :material-account-supervisor: 役割分担

このリポジトリは以下 3 者で運用する。

=== ":material-account-tie: user"

    最終判断と受け入れ。 ==下記 4 領域だけ== が必ず user 確認:

    1. 公開記事の削除 / 書き換え (content judgment)
    2. X 投稿解放 / 新カテゴリ解放 (SNS / scope)
    3. MVP scope の拡張 / 縮小
    4. 法務 / 著作権 / プライバシー / 金銭負担増 / 外部 API 課金増

    炎上対応は Claude Code が 1 次対応 (rollback 含む) し、 その後 user へ報告。

=== ":material-robot: Claude Code (主開発)"

    通常の開発 + deploy + 管理を担当する主 lane。

    具体: src / tests / config / Dockerfile / cloudbuild の編集、 commit / push、 build、 deploy、 traffic 切替、 scheduler 操作、 secret 操作、 ticket 管理、 監査、 read-only 観測。

=== ":material-robot-confused: Codex (補助開発)"

    必要時に Claude Code から fire される ==補助 lane==。

    用途の例:

    - 並列 lane が必要な時 (Claude が 1 件作業中に、 別 scope の小さい仕事を並走)
    - 長時間の単純作業 (大規模 grep / 単純 refactor / fixture 作成 等)
    - Claude の context を温存したい時

    main lane は Claude 直接、 ==Codex は適材適所で使う== (常時並走ではない)。
    どちらを使うかは Claude Code の判断。

=== ":material-chat-question: ChatGPT (会議室)"

    制度設計 / 文書の型 / 論点の圧縮補助。
    現場の deploy / publish / env 決定者にはならない。

## :material-shield-check: 報告フォーマット

中間 fire / commit / push / build / deploy / flip / verify は Claude Code で完結する。
user に上げる報告は以下 2 つの形式。

=== ":material-format-list-numbered: 結果報告 (4 行)"

    | 項目 | 内容 |
    | --- | --- |
    | A. やったこと | 何を実行したか |
    | B. 結果 | 成功 / 失敗、 数値 / 状態 |
    | C. 異常 | あれば 1 行、 なければ「なし」 |
    | D. 次やること | 次の自分のアクション |

=== ":material-help-circle: 判断要求 (3 択)"

    user の判断が必要な時の選択肢:

    - **GO**: 推奨案で進める
    - **HOLD**: 一旦停止して様子見
    - **ROLLBACK**: 直前の状態に戻す

## :material-cancel: 絶対禁止

- `.env` を shell で `source` しない (特殊文字で漏れる、 `python-dotenv` 経由)
- Secret Manager の値を chat / log / commit / メールに貼らない
- `auth.json` の内容を出さない
- 本番リソース変更を user 確認なしで実行 (上 4 領域に該当する場合のみ確認)
- マスコミ X 引用の literal コピー (oEmbed のみ可)
- 長文引用 (引用が主にならないよう注意)

## :material-traffic-light: 品質ゲートの優先順位

- 本文 NG なら publish しない (Gemini で穴埋め禁止、 source 不足は skip / review)
- subtype 100% 自動分類は狙わない (LLM 分類禁止)
- タイトルは 3 token literal assembly (player / quote / event)、 LLM rewrite 禁止
- 報知 priority + 模倣しない (一次 source は report、 編集枠は独自)

## :material-folder-multiple: 既存 doc との関係

| 場所 | 用途 |
| --- | --- |
| `CLAUDE.md` | Claude Code の恒久行動規範 |
| `AGENTS.md` | Codex / 他 agent 用の恒久制約 |
| `doc/README.md` | チケット priority board (詳細) |
| `doc/active/assignments.md` | 1 page dashboard (active ticket / blocker) |
| `doc/active/` / `doc/waiting/` / `doc/done/YYYY-MM/` | ticket 本体 |
| `docs/handoff/master_backlog.md` | 現在地 / release readiness |
| `docs/handoff/session_logs/` | session ごとの記録 |
| `mkdocs_docs/` (この site) | 安定した仕様 doc (wiki 風) |

mkdocs site は active ticket state を写さない。
GitHub Issues / `doc/` をミラーしない (一次 source は GitHub と `doc/` 側)。

## :material-stop-circle: hard stop の境界

publish を止める判断は以下 6 つに限定:

1. 本物の重複記事
2. placeholder / template 残り
3. 事実破綻
4. entity mismatch (人物違い)
5. 巨人と完全無関係
6. 本文崩壊

それ以外 (OB 非野球 / SNS 適性弱 / 巨人 relevance 弱) は publish 維持。
SNS 投稿は user 手動、 Claude Code は SNS への自動投稿は触らない。

## :material-link: 関連

- [Deploy 手順](deploy.md)
- [Env / フィーチャーフラグ](env-flags.md)
- [Cloud Scheduler 一覧](scheduler.md)
