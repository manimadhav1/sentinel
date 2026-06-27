from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


class AmbiguousField(BaseModel):
    field_name: str
    extracted_value: Any
    confidence: float
    reason: str
    suggested_value: Optional[Any] = None


class EngineResult(BaseModel):
    """
    Universal return type for every engine in the pipeline.
    Every engine accepts structured input and returns this shape.
    """
    stage: str                          # document | processing | validation | invoice
    status: str                         # SUCCESS | AMBIGUOUS | FAILED
    confidence: float = 1.0            # 0.0 – 1.0
    requires_human_review: bool = False
    next_action: str = "PROCEED"        # PROCEED | HUMAN_REVIEW | RETRY | ABORT
    data: Optional[dict] = None         # serialised output payload
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ambiguous_fields: list[AmbiguousField] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    def is_ok(self) -> bool:
        return self.status == "SUCCESS" and not self.requires_human_review

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.status = "FAILED"
        self.next_action = "ABORT"

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def flag_for_review(self, reason: str) -> None:
        self.requires_human_review = True
        self.next_action = "HUMAN_REVIEW"
        self.status = "AMBIGUOUS"
        self.add_warning(reason)


class ValidationCheck(BaseModel):
    rule: str
    passed: bool
    severity: str = "ERROR"    # ERROR | WARNING
    message: str


class ValidationReport(BaseModel):
    checks: list[ValidationCheck] = Field(default_factory=list)
    overall: str = "VALID"     # VALID | INVALID | WARN

    def add_check(self, rule: str, passed: bool,
                  message: str, severity: str = "ERROR") -> None:
        self.checks.append(ValidationCheck(
            rule=rule, passed=passed, severity=severity, message=message
        ))
        if not passed:
            if severity == "ERROR":
                self.overall = "INVALID"
            elif severity == "WARNING" and self.overall == "VALID":
                self.overall = "WARN"
