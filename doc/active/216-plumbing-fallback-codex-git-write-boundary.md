# 216 plumbing fallback / Codex git write boundary 運用プロトコル(doc-only spec)

## 1. meta

- number: 216
- type: spec / operational protocol
- status: REVIEW_NEEDED
- priority: P0.5
- lane: Claude(spec)/ 全 Codex(遵守)
- created: 2026-04-27
- parent: 193 / 207 / 211 / 213 / 214(過去事故事例)

## 2. Background — 過去事故事例 5 件

**193 / 192** では plumbing fallback で commit object 自体は着地したが、default index が同期されず `git status` が汚れたまま残った。結果として commit 済みのつもりでも staged 状態が worktree に残留し、その後の便に混入し得る状態が発生した。修復便は 193 で、partial cleanup に留まった。

**207 (`a4c3974`)** では別 Codex が古い base を持ったまま doc 変更を commit し、202 / 203 / 205 の doc 削除事故と 199 の active→waiting 移動が逆方向に巻き戻された。repo 上は commit 自体が成立しても、base 不一致のまま attach すると復元便ではなく削除便になり得ることが顕在化した。修復便は 211 (`ad729b4`)。

**211 (`ad729b4`)** は 207 事故の復元便だったが、復元対象以外の `doc/README.md` と `doc/active/assignments.md` まで `210ce41` 基準に巻き戻し、207 / 208 row と 211 row の損失 risk を新たに生んだ。restore 系の便でも wholesale rewrite をすると、事故修復と同時に board 最新状態を壊し得ることが確認された。修復便は 213 (`fb8af40`)。

**213 (`fb8af40`)** では doc reconciliation 自体は正しかったが、`refs/heads/master` 更新が Codex 側で失敗したため、自動 attach できず Claude が別途 `git update-ref` で attach する必要があった。commit object hash が残っていたため復旧できたが、attach 前 verify と executor 分離が必要であることが明確になった。

**214 (`c1927b2`)** では既に staged されていた `OPERATING_LOCK` と `doc/waiting/197-*` の MM 状態が、`git add doc/README.md doc/active/assignments.md` を含む commit に混入した。意図は board sync だけだったが、既存 staged を読まずに commit したことで GCP boundary policy まで巻き戻された。修復便は 215 (`9d48c3a`)。

## 3. 原因分析(共通要因)

- Codex sandbox では `.git` が read-only mount となることがあり、通常の `git commit` / `git update-ref` が失敗する。
- その回避として plumbing fallback(`git write-tree` + `git commit-tree` + `git update-ref`)で commit object を作れるが、default index は自動同期されない。
- その結果、working tree や default index に staged D / A / M が残り、次の commit に意図せず混入する。
- 並走便が古い HEAD を base にしたまま進むと、restore 便でも逆方向の削除や移動が起きる。
- `doc/README.md` / `doc/active/assignments.md` のような MM ステートの責任範囲が曖昧だと、partial commit が board 巻き戻し commit になりやすい。

## 4. 標準手順 — Codex commit object → Claude attach

### 4.1 Codex 便側

Codex 便は、`.git` writable 可否に依存せず **isolated temp index で commit object を作る**前提で prompt を組む。default index を使う通常 `git add` / `git commit` は、既存 staged 汚染の吸い込み risk があるため標準手順にしない。

標準 runbook:

```bash
GIT_INDEX_FILE=/tmp/git-index-<NN> git read-tree HEAD
GIT_INDEX_FILE=/tmp/git-index-<NN> git update-index --add <files>
NEW_TREE=$(GIT_INDEX_FILE=/tmp/git-index-<NN> git write-tree)
NEW_COMMIT=$(echo "<message>" | git commit-tree "$NEW_TREE" -p HEAD)
git update-ref refs/heads/master "$NEW_COMMIT"  # ro なら fail、Claude attach へ
```

Codex 側の義務:

- `<NN>` は ticket ごとに固有値を使い、他便の temp index を再利用しない。
- `git update-index --add` には明示 path のみを渡し、glob や `.` や `-A` を使わない。
- `git update-ref` が失敗しても **commit object hash を必ず完了報告に残す**。hash があれば Claude が attach できる。
- 既存 commit には touch しない。rebase / amend / reset / branch rewrite は禁止。
- attach できなかった場合でも「commit object 作成済 / attach 未了」として明示し、成功扱いにしない。

### 4.2 Claude attach 側

Claude は attach 前に **verify を通過した commit object だけ**を `refs/heads/master` に付ける。commit hash を受け取っただけで即 attach しない。

attach 前 verify 手順:

1. `git show <hash> --stat` で content と対象 file を確認する。
2. `git diff-tree --no-commit-id --name-status -r <hash> --` で D / A / M を列挙し、意図外 path が無いか確認する。
3. 期待 file path のみであることを目視 verify し、不可触 file が無いことを確認する。

attach 実行:

```bash
git update-ref refs/heads/master <hash> <prev_hash>
git log --oneline -3
git push origin master
```

attach 後 sanity:

```bash
git status --short | head -10
git diff --cached --name-status
git diff origin/master..HEAD --name-status
```

期待値:

- `git diff --cached --name-status` は空
- `origin/master..HEAD` は今回 attach した commit 内容のみ
- 想定外 file が 1 つでも出たら push 前に停止

## 5. staged D/A 混入 prevention checklist

Codex 便 prompt には以下の stop 条件を必ず含める。

- staged D / A / M が **明示 stage 対象 path 以外**にあれば即停止する。
- commit object 作成前に `git diff --cached --name-status | head -20` を確認し、空または明示対象のみであることを確認する。
- 不可触 file の staged 状態が混じっていたら commit を続行せず、restore runbook を出して停止する。
- default index が汚れている時に、そのまま `git add <target>` で上積みしない。
- cleanup はあくまで runbook 提示に留め、実行は Claude / user 判断とする。

restore runbook 例:

```bash
git restore --staged --source=HEAD -- <unrelated_files>
```

補足:

- temp index を使う場合でも、default index が既に汚れている事実は報告対象とする。
- `git diff --cached` が空でも、`git status --short` に不可触 file の staged / unstaged 混在があれば完了報告で明示する。

## 6. attach 前 verify 義務化

Claude が attach する前に、以下を **毎回必ず実行**する。214 の再発防止として、1 項目でも未確認なら attach しない。

- [ ] `git show <commit_hash> --stat` で commit 内容確認
- [ ] `git diff-tree --no-commit-id --name-status -r <commit_hash> --` で D / A / M list verify
- [ ] 不可触 file が含まれていないことを path level で確認
- [ ] 既存 staged 状態と commit 内容が同じものを参照していないか確認
- [ ] 期待 file path 以外があれば attach せず Claude 判断

verify 不通過時の扱い:

- attach 中止
- restore / cleanup 用の別便を起票
- 必要なら commit object hash は保全し、attach は後続判断に回す

## 7. 並走便間の base 不一致 prevention

- 並走中の Codex 便は **完全 file-disjoint** を原則とする。
- 同 path への並走は直列 lock とし、特に `doc/README.md` と `doc/active/assignments.md` は 1 便ずつしか touch しない。
- restore 便と新規便は同時に走らせない。207 → 211 のように、復元中に別便が動くと再巻き戻しが起こる。
- commit object 作成前に `git rev-parse --short HEAD` を記録し、完了報告に base を残す。
- Claude 側は attach 前に `prev_hash` と Codex 報告 base が一致しているか確認し、不一致なら attach を保留する。

## 8. 過去 5 件の lessons learned

- **193**: plumbing fallback と default index は別物であり、commit object ができても `git status` は信用できない。status 不信を明文化する。
- **207**: 別 Codex の base 確認を省略すると、復元ではなく削除事故になる。最新 HEAD を base にする義務を持たせる。
- **211**: restore 便でも既存 row を保持する。`README` / `assignments` の wholesale rewrite は禁止する。
- **213**: attach は別責務であり、事前 verify を通さずに ref を進めない。
- **214**: 既存 staged を読まずに `git add` すると、別 scope の MM が混入する。`git add -A` 禁止だけでは不十分で、staged inspection を必須にする。

参考メモとして、193 系で顕在化した「plumbing fallback と default index のズレ」は `feedback_git_commit_plumbing_fallback.md` で扱われた論点として継続参照対象にする。

## 9. acceptance(計画段階)

- 5 過去事故が commit hash と修復便つきで記録されている。
- 原因分析として 5 共通要因が list されている。
- Codex commit object 作成から Claude attach までの標準手順が明文化されている。
- staged D / A 混入 prevention checklist が運用 runbook として利用可能である。
- attach 前 verify 5 項目が checklist 形式で記載されている。

## 10. non-goals(本便でやらないこと)

- `.git` read-only 解消や Codex sandbox 設定変更などの実装修正
- Codex sandbox の git config 書き換え
- 過去 commit の rebase / repair / rewrite
- 専用 deploy executor の実装
- README / assignments / OPERATING_LOCK の同期更新
- src / tests / GCP / WP / mail / X / scheduler / secret / `.env` への変更

## 11. 将来の検討事項

- 217 / 218 などの後続 ticket で、Codex sandbox の `.git` rw 設定要求を検討する。
- attach を Claude 手作業に依存させない専用 deploy executor の実装を検討する。
- ただし、repo / GCP / runtime 設定変更を伴うため user 判断を前提とする。
