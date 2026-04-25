from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskType(str, Enum):
    UNSUPPORTED_NAMED_FACT = "unsupported_named_fact"
    UNSUPPORTED_NUMERIC_FACT = "unsupported_numeric_fact"
    UNSUPPORTED_DATE_TIME_FACT = "unsupported_date_time_fact"
    UNSUPPORTED_QUOTE = "unsupported_quote"
    UNSUPPORTED_ATTRIBUTION = "unsupported_attribution"
    CONTRADICTION = "contradiction"
    SOURCE_MISMATCH = "source_mismatch"
    SPECULATIVE_CLAIM = "speculative_claim"
    STALE_OR_TIME_SENSITIVE = "stale_or_time_sensitive"


class Operation(str, Enum):
    REPLACE = "replace"
    DELETE = "delete"
    SOFTEN = "soften"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be bool")
    return value


def _require_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be int")
    return value


def _require_str(value: Any, field_name: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be str")
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must be non-empty")
    return value


def _coerce_enum(enum_cls: type[Enum], value: Any, field_name: str):
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(str(value))
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_cls)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


@dataclass(slots=True)
class SuggestedFix:
    operation: Operation
    find_text: str
    replace_text: str
    rationale: str = ""

    def __post_init__(self) -> None:
        self.operation = _coerce_enum(Operation, self.operation, "suggested_fix.operation")
        self.find_text = _require_str(self.find_text, "suggested_fix.find_text", allow_empty=False)
        self.replace_text = _require_str(self.replace_text, "suggested_fix.replace_text")
        self.rationale = _require_str(self.rationale, "suggested_fix.rationale")
        if self.operation in {Operation.REPLACE, Operation.SOFTEN} and not self.replace_text:
            raise ValueError("suggested_fix.replace_text must be non-empty for replace/soften")

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation.value,
            "find_text": self.find_text,
            "replace_text": self.replace_text,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SuggestedFix:
        if not isinstance(payload, dict):
            raise ValueError("suggested_fix must be a mapping")
        return cls(
            operation=payload.get("operation"),
            find_text=payload.get("find_text"),
            replace_text=payload.get("replace_text"),
            rationale=payload.get("rationale", ""),
        )


@dataclass(slots=True)
class DetectorFinding:
    severity: Severity
    risk_type: RiskType
    target: str
    evidence_excerpt: str
    why_risky: str
    suggested_fix: SuggestedFix

    def __post_init__(self) -> None:
        self.severity = _coerce_enum(Severity, self.severity, "finding.severity")
        self.risk_type = _coerce_enum(RiskType, self.risk_type, "finding.risk_type")
        self.target = _require_str(self.target, "finding.target", allow_empty=False)
        self.evidence_excerpt = _require_str(self.evidence_excerpt, "finding.evidence_excerpt")
        self.why_risky = _require_str(self.why_risky, "finding.why_risky")
        if not isinstance(self.suggested_fix, SuggestedFix):
            raise ValueError("finding.suggested_fix must be SuggestedFix")

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "risk_type": self.risk_type.value,
            "target": self.target,
            "evidence_excerpt": self.evidence_excerpt,
            "why_risky": self.why_risky,
            "suggested_fix": self.suggested_fix.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DetectorFinding:
        if not isinstance(payload, dict):
            raise ValueError("finding must be a mapping")
        return cls(
            severity=payload.get("severity"),
            risk_type=payload.get("risk_type"),
            target=payload.get("target"),
            evidence_excerpt=payload.get("evidence_excerpt", ""),
            why_risky=payload.get("why_risky", ""),
            suggested_fix=SuggestedFix.from_dict(payload.get("suggested_fix", {})),
        )


@dataclass(slots=True)
class DetectorResult:
    post_id: int
    content_hash: str
    overall_severity: Severity
    is_4_17_equivalent_risk: bool
    findings: list[DetectorFinding] = field(default_factory=list)
    safe_to_publish_after_fixes: bool = True
    notes: str = ""

    def __post_init__(self) -> None:
        self.post_id = _require_int(self.post_id, "post_id")
        self.content_hash = _require_str(self.content_hash, "content_hash", allow_empty=False)
        self.overall_severity = _coerce_enum(Severity, self.overall_severity, "overall_severity")
        self.is_4_17_equivalent_risk = _require_bool(
            self.is_4_17_equivalent_risk,
            "is_4_17_equivalent_risk",
        )
        self.safe_to_publish_after_fixes = _require_bool(
            self.safe_to_publish_after_fixes,
            "safe_to_publish_after_fixes",
        )
        self.notes = _require_str(self.notes, "notes")
        validated_findings: list[DetectorFinding] = []
        for finding in self.findings:
            if isinstance(finding, DetectorFinding):
                validated_findings.append(finding)
            else:
                validated_findings.append(DetectorFinding.from_dict(finding))
        self.findings = validated_findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_id": self.post_id,
            "content_hash": self.content_hash,
            "overall_severity": self.overall_severity.value,
            "is_4_17_equivalent_risk": self.is_4_17_equivalent_risk,
            "findings": [finding.to_dict() for finding in self.findings],
            "safe_to_publish_after_fixes": self.safe_to_publish_after_fixes,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DetectorResult:
        if not isinstance(payload, dict):
            raise ValueError("detector result must be a mapping")
        return cls(
            post_id=payload.get("post_id"),
            content_hash=payload.get("content_hash"),
            overall_severity=payload.get("overall_severity"),
            is_4_17_equivalent_risk=payload.get("is_4_17_equivalent_risk"),
            findings=payload.get("findings", []),
            safe_to_publish_after_fixes=payload.get("safe_to_publish_after_fixes", True),
            notes=payload.get("notes", ""),
        )


@dataclass(slots=True)
class ApprovalFinding:
    finding_index: int
    severity: Severity
    risk_type: RiskType
    target: str
    evidence_excerpt: str
    why_risky: str
    suggested_fix: SuggestedFix
    approve: bool = False

    def __post_init__(self) -> None:
        self.finding_index = _require_int(self.finding_index, "finding_index")
        self.severity = _coerce_enum(Severity, self.severity, "severity")
        self.risk_type = _coerce_enum(RiskType, self.risk_type, "risk_type")
        self.target = _require_str(self.target, "target", allow_empty=False)
        self.evidence_excerpt = _require_str(self.evidence_excerpt, "evidence_excerpt")
        self.why_risky = _require_str(self.why_risky, "why_risky")
        if not isinstance(self.suggested_fix, SuggestedFix):
            raise ValueError("suggested_fix must be SuggestedFix")
        self.approve = _require_bool(self.approve, "approve")

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_index": self.finding_index,
            "severity": self.severity.value,
            "risk_type": self.risk_type.value,
            "target": self.target,
            "evidence_excerpt": self.evidence_excerpt,
            "why_risky": self.why_risky,
            "suggested_fix": self.suggested_fix.to_dict(),
            "approve": self.approve,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ApprovalFinding:
        if not isinstance(payload, dict):
            raise ValueError("approval finding must be a mapping")
        return cls(
            finding_index=payload.get("finding_index"),
            severity=payload.get("severity"),
            risk_type=payload.get("risk_type"),
            target=payload.get("target"),
            evidence_excerpt=payload.get("evidence_excerpt", ""),
            why_risky=payload.get("why_risky", ""),
            suggested_fix=SuggestedFix.from_dict(payload.get("suggested_fix", {})),
            approve=payload.get("approve"),
        )


@dataclass(slots=True)
class ApprovalRecord:
    post_id: int
    content_hash: str
    overall_severity: Severity
    is_4_17_equivalent_risk: bool
    safe_to_publish_after_fixes: bool
    findings: list[ApprovalFinding] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        self.post_id = _require_int(self.post_id, "post_id")
        self.content_hash = _require_str(self.content_hash, "content_hash", allow_empty=False)
        self.overall_severity = _coerce_enum(Severity, self.overall_severity, "overall_severity")
        self.is_4_17_equivalent_risk = _require_bool(
            self.is_4_17_equivalent_risk,
            "is_4_17_equivalent_risk",
        )
        self.safe_to_publish_after_fixes = _require_bool(
            self.safe_to_publish_after_fixes,
            "safe_to_publish_after_fixes",
        )
        self.notes = _require_str(self.notes, "notes")
        validated_findings: list[ApprovalFinding] = []
        seen_indices: set[int] = set()
        for finding in self.findings:
            item = finding if isinstance(finding, ApprovalFinding) else ApprovalFinding.from_dict(finding)
            if item.finding_index in seen_indices:
                raise ValueError(f"duplicate finding_index: {item.finding_index}")
            seen_indices.add(item.finding_index)
            validated_findings.append(item)
        self.findings = validated_findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_id": self.post_id,
            "content_hash": self.content_hash,
            "overall_severity": self.overall_severity.value,
            "is_4_17_equivalent_risk": self.is_4_17_equivalent_risk,
            "safe_to_publish_after_fixes": self.safe_to_publish_after_fixes,
            "findings": [finding.to_dict() for finding in self.findings],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ApprovalRecord:
        if not isinstance(payload, dict):
            raise ValueError("approval record must be a mapping")
        return cls(
            post_id=payload.get("post_id"),
            content_hash=payload.get("content_hash"),
            overall_severity=payload.get("overall_severity"),
            is_4_17_equivalent_risk=payload.get("is_4_17_equivalent_risk"),
            safe_to_publish_after_fixes=payload.get("safe_to_publish_after_fixes"),
            findings=payload.get("findings", []),
            notes=payload.get("notes", ""),
        )
