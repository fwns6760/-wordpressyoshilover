# 031 — 027 canary success 判定と証跡チェックリスト固定

**フェーズ：** 027 canary gate 固定  
**担当：** Claude Code  
**依存：** 027, 028

---

## why_now

- `027` は success 維持だが、`031` の gate 定義が旧 canary ベースのままだと実運用 success の pass / fail 判定が runtime issue と混線する。
- `canary` はこれまで実運用 success の略として使ってきたが、本便で「実運用 Draft 4 条件 pass」に再定義する。
- `029` は `027 canary success` 後 gate のため、ここを先に固定しないと現場が自律的に次便へ進めない。

## purpose

- `027 canary success` の成功条件、証跡、stop 条件、`029` 解放条件を 1 ticket で固定する。
- `canary` は実運用 success の略として扱い、本便では実運用 Draft 4 条件 pass に再定義する。
- Codex exec 経路 canary の DNS/sandbox runtime issue は別線隔離し、現場が追加確認なしで判定できるようにする。

## scope

### 実走経路の扱い

- `user 手元 runner` / `Codex exec` / `host 直実行` / `sandbox 例外` は区別して記録するが、success 判定の主軸は「実運用 Draft が WordPress に validator pass で入ったか」とする。
- Codex exec 経路 canary の DNS/sandbox runtime issue は runtime 観測の別線事項であり、`031` gate 条件には含めない。
- 代替検証(read-only)は blocker triage 用であり、`027 実運用 success` 判定には使わない。

### 実運用 success 条件(4 条件 pass)

- `validator`: 実運用 Draft の validator pass を、WordPress 上の path-limited 証跡で確認できる。
- `wp_post_dry_run`: `wp_post_dry_run = pass`
- `source_fetch`: `source_fetch = pass`
- `duplicate_skip`: 同一 `candidate_key` 再走で `duplicate_skip=true` かつ `existing_post_ids` が整合する。
- Draft に `candidate_id / subtype / category / tags / source_trust=primary` が反映される。
- 同一 `candidate_id` または同等 `candidate_key` で 2 件目が作られていない。
- `published` への書き込みがない。
- mail / automation / env / secret に副作用がない。

### 証跡チェックリスト

- 使用した実行経路(`user 手元 runner` / `Codex exec` / その他)と、その経路が `027` 本体 success 判定の必須条件ではないこと
- 実行コマンドまたは task id
- path-limited の `git log --stat`
- path-limited の `git status --short`
- WP 応答の post id / status / metadata
- duplicate 未発生を示す照会結果
- pass / stop の最終判定メモ
- 4 条件の pass 判定(`validator` / `wp_post_dry_run` / `source_fetch` / `duplicate_skip`)を 1 行ずつ明記する

### stop 条件

- DNS 未解消（ただし、Codex exec 経路 canary の DNS/sandbox runtime issue は `031` の stop 条件ではなく、実運用 Draft 経路での fetch 失敗だけを stop とする）
- `status=draft` 未到達
- metadata 欠落
- duplicate 発生
- `published` への誤書き込み
- mail / automation / env / secret への副作用

### 029 解放条件

- 4 条件(`validator` / `wp_post_dry_run` / `source_fetch` / `duplicate_skip`)を全 pass し、stop 条件が 1 つも発生していない時だけ `029` を READY にする。
- 1 つでも stop 条件に触れたら `029` は blocked のまま維持する。

## non_goals

- DNS 自体の解消
- Codex exec 経路 canary の DNS/sandbox runtime issue 解消
- scheduler / mail / env / secret の変更
- 残 3 subtype の起票
- `029` の実装着手

## acceptance_check

- 4 条件 pass が別人が読んでも同じ pass / fail 判定になる。
- `029` を fire してよい条件と、止める条件が 1 ticket で読める。
- 代替検証(read-only)が success 判定に使えないことが明記されている。
- Codex exec 経路 canary の DNS/sandbox runtime issue が `031` gate 条件外として別線隔離されていることが明記されている。

## TODO

【×】実走パスの優先順位を固定する  
【×】canary success 条件を固定する  
【×】証跡チェックリストを固定する  
【×】stop 条件を固定する  
【×】`029` 解放条件を固定する  
【×】代替検証は triage 用で success 判定に使わないと明記する  

## 成功条件

- 現場の Claude Code が user 追加確認なしで `027 実運用 success` を 4 条件で判定できる  
- `029` をいつ fire してよいかが ticket 単体で読める  
- `027` 実運用 success の pass / fail 証跡が path-limited に追認できる  
