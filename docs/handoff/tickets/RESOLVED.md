# Resolved Tickets

解決済みチケットのアーカイブ。

## フォーマット

```markdown
## T-XXX [優先度] タイトル

**発見日**: YYYY-MM-DD
**解決日**: YYYY-MM-DD
**解決者**: Yoshihiro / Claude Opus / Codex / Claude Code
**対応内容**: 何をして解決したか
**関連commit**: <hash> （あれば）
```

---

## T-003 🟠 ヨシラバーの「現在のdraft件数」が不明

**発見日**: 2026-04-18
**解決日**: 2026-04-18
**解決者**: Codex（実装）/ Claude Code（依頼ドラフト）
**対応内容**:
- 案B（Cloud Logging 候補 post_id + WP 単独 GET）を採用
- `src/draft_inventory_from_logs.py` と `tests/test_draft_inventory_from_logs.py` を追加
- CLI: `python3 -m src.draft_inventory_from_logs --days 7 [--json]`
- T-001 の list API 不全を迂回、single GET で status=draft を確定できる

**確認された現在の draft 件数（2026-04-18時点）**:
- **total: 77 件**
- subtype 別: lineup=29, player=11, farm=11, postgame=9, manager=7, pregame=4, general=3, farm_lineup=2, roster=1
- category 別: 試合速報=42, 選手情報=11, 首脳陣=7, ドラフト・育成=13, コラム=3, 補強・移籍=1

**関連commit**: `10fa214`

---

