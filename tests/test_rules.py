from rules import evaluate_numeric_requirement


def test_numeric_rule_passes_explicit_sla():
    result = evaluate_numeric_requirement(
        "业务连续性不低于 99.9%",
        "本项目承诺业务连续性达到 99.99%。",
    )
    assert result["status"] == "pass"
    assert result["observed"] == 99.99


def test_numeric_rule_fails_explicit_recovery_time():
    result = evaluate_numeric_requirement(
        "故障恢复时间不超过 30 分钟",
        "故障恢复时间为 45 分钟。",
    )
    assert result["status"] == "fail"


def test_numeric_rule_refuses_ambiguous_evidence():
    result = evaluate_numeric_requirement(
        "故障恢复时间不超过 30 分钟",
        "一般故障 15 分钟，重大故障 45 分钟。",
    )
    assert result["status"] == "no_numeric_evidence"


def test_numeric_rule_skips_non_numeric_requirement():
    result = evaluate_numeric_requirement(
        "应提供完善的运维保障方案",
        "我方提供全天候运维保障方案。",
    )
    assert result["status"] == "not_applicable"
