from requirement_extractor import extract_requirements
from schemas import RequirementBatch, RequirementDraft


class FakeLLM:
    def invoke(self, _prompt):
        return RequirementBatch(
            requirements=[
                RequirementDraft(
                    dimension="SLA",
                    expected="业务连续性不低于 99.99%",
                    mandatory=True,
                    level="重要",
                    source_quote="★业务连续性不低于 99.99%",
                    source_block_index=1,
                ),
                RequirementDraft(
                    dimension="供电",
                    expected="虚构要求",
                    mandatory=False,
                    level="一般",
                    source_quote="输入中不存在的句子",
                    source_block_index=1,
                ),
            ]
        )


def test_extractor_keeps_only_source_grounded_requirements(monkeypatch):
    monkeypatch.setattr(
        "requirement_extractor.parse_docx",
        lambda _path: {
            "text_chunks": [
                {
                    "block_index": 1,
                    "section": "技术要求",
                    "text": "★业务连续性不低于 99.99%",
                }
            ]
        },
    )
    result = extract_requirements("tender.docx", llm=FakeLLM())
    assert len(result) == 1
    assert result[0].mandatory is True
    assert result[0].level == "废标红线"
    assert result[0].tender_quote == "★业务连续性不低于 99.99%"
    assert result[0].tender_evidence_id.startswith("tender_")
