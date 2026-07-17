from audit_agent import audit_one
from schemas import AuditDecision, EvidenceCitation


class FakeLLM:
    def __init__(self, result):
        self.result = result

    def invoke(self, _prompt):
        return self.result


def test_citation_must_come_from_current_retrieval_window(monkeypatch):
    monkeypatch.setattr(
        "audit_agent.query",
        lambda *args, **kwargs: [
            {
                "type": "text",
                "content": "业务连续性不低于99.99%",
                "evidence_id": "ev_current",
                "source": "response.docx",
                "section": "SLA",
            }
        ],
    )
    monkeypatch.setattr(
        "audit_agent._get_llm",
        lambda: FakeLLM(
            AuditDecision(
                conclusion="达标",
                reason="应标承诺满足要求",
                citations=[
                    EvidenceCitation(
                        evidence_id="ev_current", quote="业务连续性不低于99.99%"
                    )
                ],
            )
        ),
    )
    result = audit_one(
        {
            "id": "sla",
            "dimension": "SLA",
            "query": "业务连续性",
            "expect": "不低于99.9%",
            "level": "废标红线",
        },
        vs=object(),
    )
    assert result["citation_valid"] is True
    assert result["source"] == "ev_current"
    assert result["retrieved_evidence_ids"] == ["ev_current"]


def test_out_of_window_citation_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "audit_agent.query",
        lambda *args, **kwargs: [
            {
                "type": "text",
                "content": "本段没有目标数字",
                "evidence_id": "ev_current",
                "source": "response.docx",
            }
        ],
    )
    monkeypatch.setattr(
        "audit_agent._get_llm",
        lambda: FakeLLM(
            AuditDecision(
                conclusion="达标",
                reason="错误引用其他证据",
                citations=[EvidenceCitation(evidence_id="ev_other", quote="99.99%")],
            )
        ),
    )
    result = audit_one(
        {
            "id": "sla",
            "dimension": "SLA",
            "query": "业务连续性",
            "expect": "不低于99.9%",
            "level": "废标红线",
        },
        vs=object(),
    )
    assert result["citation_valid"] is False
    assert result["ungrounded_citation_ids"] == ["ev_other"]
