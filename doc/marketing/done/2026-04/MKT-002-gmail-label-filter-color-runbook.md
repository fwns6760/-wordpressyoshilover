# MKT-002 gmail label filter color runbook

## dropped note(2026-04-29)

- status: DROPPED
- reason: Dropped. Gmail label/filter setup is not needed now; 241 already confirmed PC/mobile notification delivery.

## meta

- number: MKT-002
- alias: -
- status: DROPPED
- priority: P1
- parent: MKT-001

## Summary

`MKT-001` で固定する件名 prefix と本文 metadata を受けて、Gmail 上で「公開確認」「X投稿候補」「要確認」「警告」を見落とさず扱うための label / filter / color runbook を定義する。

## Not Goals

- Gmail filter や label の live 作成
- SMTP / sender alias の変更
- publish-notice 実装の追加変更

## Next Action

- `MKT-001` の件名 prefix と metadata block が実装で安定したら、Gmail 検索式と label 命名規則を spec 化する
