from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.pre_publish_fact_check.contracts import (
    ApprovalFinding,
    ApprovalRecord,
    DetectorResult,
)


def build_approval_records(detector_results: list[dict[str, Any]]) -> list[ApprovalRecord]:
    approvals: list[ApprovalRecord] = []
    for detector_payload in detector_results:
        detector_record = DetectorResult.from_dict(detector_payload)
        findings = [
            ApprovalFinding(
                finding_index=index,
                severity=finding.severity,
                risk_type=finding.risk_type,
                target=finding.target,
                evidence_excerpt=finding.evidence_excerpt,
                why_risky=finding.why_risky,
                suggested_fix=finding.suggested_fix,
                approve=False,
            )
            for index, finding in enumerate(detector_record.findings)
        ]
        approvals.append(
            ApprovalRecord(
                post_id=detector_record.post_id,
                content_hash=detector_record.content_hash,
                overall_severity=detector_record.overall_severity,
                is_4_17_equivalent_risk=detector_record.is_4_17_equivalent_risk,
                safe_to_publish_after_fixes=detector_record.safe_to_publish_after_fixes,
                findings=findings,
                notes=detector_record.notes,
            )
        )
    return approvals


def dump_yaml(records: list[ApprovalRecord]) -> str:
    payload = [record.to_dict() for record in records]
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def write_yaml(records: list[ApprovalRecord], path: str | Path) -> None:
    Path(path).write_text(dump_yaml(records), encoding="utf-8")


def load_yaml(path: str | Path) -> list[ApprovalRecord]:
    raw = Path(path).read_text(encoding="utf-8")
    payload = yaml.safe_load(raw)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError("approval YAML root must be a list")
    records: list[ApprovalRecord] = []
    for index, item in enumerate(payload):
        try:
            records.append(ApprovalRecord.from_dict(item))
        except ValueError as exc:
            raise ValueError(f"invalid approval YAML at index {index}: {exc}") from exc
    return records
