"""Conservative deterministic checks for simple numeric requirements.

The LLM still identifies relevant evidence and explains the decision.  This
module only handles an intentionally small, auditable subset such as
"不低于 99.99%" or "不超过 30 分钟".  Ambiguous requirements are returned as
``not_applicable`` instead of being guessed.
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict


RuleStatus = Literal["pass", "fail", "not_applicable", "no_numeric_evidence"]


class NumericRuleResult(TypedDict, total=False):
    status: RuleStatus
    operator: str
    threshold: float
    observed: float
    unit: str
    reason: str


_EXPECTATION = re.compile(
    r"(?P<operator>不低于|不少于|至少|大于等于|不高于|不超过|至多|小于等于|"
    r"大于|超过|小于|低于|>=|<=|>|<|≥|≤)"
    r"\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|％|百分比|秒|分钟|小时|天|年|个|台|套)?"
)
_NUMBER = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|％|百分比|秒|分钟|小时|天|年|个|台|套)?"
)

_NORMALIZED_OPERATOR = {
    "不低于": ">=",
    "不少于": ">=",
    "至少": ">=",
    "大于等于": ">=",
    ">=": ">=",
    "≥": ">=",
    "不高于": "<=",
    "不超过": "<=",
    "至多": "<=",
    "小于等于": "<=",
    "<=": "<=",
    "≤": "<=",
    "大于": ">",
    "超过": ">",
    ">": ">",
    "小于": "<",
    "低于": "<",
    "<": "<",
}


def _normalize_unit(unit: str | None) -> str:
    if unit in {"％", "百分比"}:
        return "%"
    return unit or ""


def _compare(observed: float, operator: str, threshold: float) -> bool:
    return {
        ">=": observed >= threshold,
        "<=": observed <= threshold,
        ">": observed > threshold,
        "<": observed < threshold,
    }[operator]


def evaluate_numeric_requirement(
    expected: str, evidence_text: str
) -> NumericRuleResult:
    """Evaluate one explicit threshold against a short cited evidence span.

    Only one threshold and one compatible observed value are accepted.  If the
    text contains multiple compatible values, the function refuses to choose
    between them and leaves the decision to human/LLM review.
    """

    matches = list(_EXPECTATION.finditer(expected))
    if len(matches) != 1:
        return {
            "status": "not_applicable",
            "reason": "要求中没有唯一、可确定执行的数值阈值。",
        }

    expected_match = matches[0]
    operator = _NORMALIZED_OPERATOR[expected_match.group("operator")]
    threshold = float(expected_match.group("value"))
    unit = _normalize_unit(expected_match.group("unit"))

    candidates: list[float] = []
    for match in _NUMBER.finditer(evidence_text):
        candidate_unit = _normalize_unit(match.group("unit"))
        if unit and candidate_unit != unit:
            continue
        if not unit and candidate_unit:
            continue
        candidates.append(float(match.group("value")))

    if len(candidates) != 1:
        return {
            "status": "no_numeric_evidence",
            "operator": operator,
            "threshold": threshold,
            "unit": unit,
            "reason": "引用证据中没有唯一且单位一致的响应数值。",
        }

    observed = candidates[0]
    passed = _compare(observed, operator, threshold)
    symbol = unit or "（无单位）"
    return {
        "status": "pass" if passed else "fail",
        "operator": operator,
        "threshold": threshold,
        "observed": observed,
        "unit": unit,
        "reason": (
            f"确定性校验：响应值 {observed:g}{symbol} "
            f"{'满足' if passed else '不满足'} {operator} {threshold:g}{symbol}。"
        ),
    }
