from review_workflow import dispatch_requirements, route_after_audit


def test_dispatch_creates_one_parallel_task_per_requirement():
    sends = dispatch_requirements(
        {
            "document_id": "doc1",
            "requirements": [{"requirement_id": "r1"}, {"requirement_id": "r2"}],
        }
    )
    assert len(sends) == 2
    assert all(send.node == "audit_requirement" for send in sends)


def test_redline_risk_can_route_to_human_review():
    state = {
        "require_human_review": True,
        "results": [
            {"mandatory": True, "level": "废标红线", "conclusion": "风险"}
        ],
    }
    assert route_after_audit(state) == "human_review"
    state["require_human_review"] = False
    assert route_after_audit(state) == "finish"
