# 203 ticket number reservation rule

- priority: P0.5
- status: CLOSED
- owner: Claude / Codex A or B
- lane: either
- parent: 188 / 189 / 192 / 200 / 201

## Close note(2026-04-28)

- numbering / reservation rule is reflected in `doc/README.md`.
- current active lanes are Codex A / Codex B only; Codex-M is not an active dispatch target.

## Goal

- stop ticket-number collisions before work is delegated
- keep README as the single visible reservation ledger

## Rule

- reserve a new number in `doc/README.md` before firing work to Claude / Codex A / Codex B
- `1 number = 1 scope`
- multiple commits under the same number are allowed only when they belong to that one scope:
  - spec
  - implementation
  - doc sync
  - narrow follow-up within the same acceptance
- do not mix unrelated purposes under the same number
- commit message default is `<number>: <summary>`

## If Conflict Is Found Later

- do not silently reuse the number again
- record the cleanup in the next doc-only sync
- separate the scopes onto distinct ticket numbers from that point onward

## Historical Examples

- `188` collided across:
  - IAM fix runbook `74ccef6`
  - manual X candidates impl `1ac710b`
  - ticket spec `b6b2b2b`
  - this was later separated by `190` / `191`
- `189` collided across:
  - contextual X candidates impl `b7a9e1f`
  - ticket doc `987bae7`
- `192` is the normal case:
  - two doc commits
  - one scope
  - same ticket number kept

## Acceptance

- README numbering policy states reservation-first
- the `1 number = 1 scope` rule is explicit
- the default commit-message shape is fixed
- future conflicts have a documented cleanup path
