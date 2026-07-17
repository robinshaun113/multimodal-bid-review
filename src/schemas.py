"""Typed contracts for tender requirements, evidence and compliance results."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field


Conclusion = Literal["达标", "缺失", "风险"]
RiskLevel = Literal["废标红线", "重要", "一般", "技术展示", "次要"]


class Requirement(BaseModel):
    requirement_id: str
    dimension: str
    query: str
    expected: str
    level: RiskLevel = "一般"
    mandatory: bool = False
    tender_evidence_id: str | None = None
    tender_quote: str = ""
    tender_section: str = ""
    origin: Literal["tender", "baseline"] = "tender"

    def as_legacy_item(self) -> dict:
        return {
            "id": self.requirement_id,
            "dimension": self.dimension,
            "query": self.query,
            "expect": self.expected,
            "level": self.level,
            "mandatory": self.mandatory,
            "tender_evidence_id": self.tender_evidence_id,
            "tender_quote": self.tender_quote,
            "origin": self.origin,
        }


class RequirementDraft(BaseModel):
    dimension: str = Field(description="需求类别，如SLA、供电、制冷、商务或图纸")
    expected: str = Field(description="应标方必须满足或响应的具体要求")
    mandatory: bool = Field(description="是否为★/▲/必须/不得等强制性要求")
    level: RiskLevel = Field(default="一般")
    source_quote: str = Field(description="招标文件中的原文短句")
    source_block_index: int = Field(description="输入块编号")


class RequirementBatch(BaseModel):
    requirements: list[RequirementDraft]


class EvidenceCitation(BaseModel):
    evidence_id: str
    quote: str = Field(description="支持结论的应标原文或图片描述短句")


class AuditDecision(BaseModel):
    conclusion: Conclusion
    reason: str
    citations: list[EvidenceCitation] = Field(default_factory=list)


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(x) for x in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:16]}"


def baseline_requirement(item: dict) -> Requirement:
    return Requirement(
        requirement_id=item["id"],
        dimension=item["dimension"],
        query=item["query"],
        expected=item["expect"],
        level=item.get("level", "一般"),
        mandatory=item.get("level") == "废标红线",
        origin="baseline",
    )
