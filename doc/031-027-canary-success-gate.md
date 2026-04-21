# 031 — 027 canary success 判定と証跡チェックリスト固定

**フェーズ：** 027 canary gate 固定  
**担当：** Claude Code  
**依存：** 027, 028

---

## why_now

- `027` は impl 済みだが、DNS blocker 解消後の pass / fail 判定が現場判断に残ると再停止する。
- `029` は `027 canary success` 後 gate のため、ここを先に固定しないと現場が自律的に次便へ進めない。

## purpose

- `027 canary success` の成功条件、証跡、stop 条件、`029` 解放条件を 1 ticket で固定する。
- DNS blocker は user 判断事項として隔離し、解消後は現場が追加確認なしで判定できるようにする。

## scope

### 実走パスの優先順位

1. `host 直実行`
2. `sandbox 例外`
3. `代替検証(read-only)`

- 1 または 2 だけが canary success 判定の対象。
- 3 は blocker triage 用であり、`027 canary success` とは見なさない。

### canary success 条件

- 対象 candidate で `status=draft` の新規 post が 1 件だけ作られる。
- post に `candidate_id / subtype / category / tags / source_trust=primary` が反映される。
- 同一 `candidate_id` または同等 `candidate_key` で 2 件目が作られていない。
- `published` への書き込みがない。
- mail / automation / env / secret に副作用がない。

### 証跡チェックリスト

- 使用した実走パスとその理由
- 実行コマンドまたは task id
- path-limited の `git log --stat`
- path-limited の `git status --short`
- WP 応答の post id / status / metadata
- duplicate 未発生を示す照会結果
- pass / stop の最終判定メモ

### stop 条件

- DNS 未解消
- `status=draft` 未到達
- metadata 欠落
- duplicate 発生
- `published` への誤書き込み
- mail / automation / env / secret への副作用

### 029 解放条件

- canary success 条件をすべて満たした時だけ `029` を READY にする。
- 1 つでも stop 条件に触れたら `029` は blocked のまま維持する。

## non_goals

- DNS 自体の解消
- scheduler / mail / env / secret の変更
- 残 3 subtype の起票
- `029` の実装着手

## acceptance_check

- DNS 解消後、別人が読んでも同じ pass / fail 判定になる。
- `029` を fire してよい条件と、止める条件が 1 ticket で読める。
- 代替検証(read-only)が success 判定に使えないことが明記されている。

## TODO

【×】実走パスの優先順位を固定する  
【×】canary success 条件を固定する  
【×】証跡チェックリストを固定する  
【×】stop 条件を固定する  
【×】`029` 解放条件を固定する  
【×】代替検証は triage 用で success 判定に使わないと明記する  

## 成功条件

- DNS blocker 解消後、現場の Claude Code が user 追加確認なしで `027 canary success` を判定できる  
- `029` をいつ fire してよいかが ticket 単体で読める  
- `027` canary の pass / fail 証跡が path-limited に追認できる  
