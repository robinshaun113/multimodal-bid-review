"""
src/audit_agent.py — 应标书审核 Agent (Day40)

把 checklist(标准) + 多模态RAG(检索) 串成自动审核：
  每项 → 拿 query 去 RAG 检索原文/图描述 → 连同 expect 标准给 LLM
  → LLM 对照判断 {达标/缺失/风险} + 依据 + 出处
防幻觉：严格约束 LLM 只依据检索到的原文，检索不到就判"缺失"，绝不编造。

用法：python src/audit_agent.py            # 跑全部 checklist
     python src/audit_agent.py <项id>     # 只审一项
"""
import os
import sys
import yaml
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

sys.path.insert(0, os.path.dirname(__file__))
from multimodal_rag import query, load_index
from schemas import AuditDecision, Requirement, baseline_requirement, stable_id
from rules import evaluate_numeric_requirement

load_dotenv(override=True)

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_CHECKLIST = os.path.join(_ROOT, "checklist.yaml")


def _get_llm():
    return ChatOpenAI(
        model=os.getenv("QWEN_TEXT_MODEL", "qwen3.7-plus"),
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0,
    ).with_structured_output(AuditDecision, method="function_calling")


def _normalize_item(item) -> Requirement:
    if isinstance(item, Requirement):
        return item
    if "requirement_id" in item:
        return Requirement.model_validate(item)
    return baseline_requirement(item)


def audit_one(item, vs=None, k=8):
    """审一项：检索 → LLM 对照 expect 判断（防幻觉）。返回 dict。

    k=8（Day46 从 4 上调）：全量入库后库里多碎片(标题/表头)，k=4 时实质内容
    常被关键词高度匹配的标题挤出证据窗口，导致'二次假缺失'。

    按维度定向检索(Day46)：只有"图纸完整性"维度需要 VLM 图描述，其余文本类
    维度只检 text——否则图描述会挤占文本证据窗口，反而漏掉文本承诺(如罚则条款)。
    """
    req = _normalize_item(item)
    is_diagram = "图纸" in req.dimension or "拓扑" in req.dimension or "布局" in req.dimension
    only_type = None if is_diagram else "text"
    hits = query(req.query, k=k, vs=vs, only_type=only_type)
    # 把检索到的证据(文本内容 / 图描述)拼成上下文
    evidence = []
    evidence_by_id = {}
    for h in hits:
        body = h.get("desc") if h["type"] == "image" else h.get("content", "")
        evidence_id = h.get("evidence_id") or stable_id(
            "legacy", h.get("source"), h.get("rid"), body
        )
        evidence_by_id[evidence_id] = body
        if h["type"] == "image":
            evidence.append(f"[{evidence_id} | 图 {h['rid']}] {body}")
        else:
            evidence.append(
                f"[{evidence_id} | {h.get('source') or '应标书'} | "
                f"章节:{h.get('section') or '未知'}] {body}"
            )
    evidence_text = "\n".join(evidence) if evidence else "（未检索到相关内容）"

    if not hits:
        return {
            "id": req.requirement_id,
            "dimension": req.dimension,
            "level": req.level,
            "mandatory": req.mandatory,
            "requirement_origin": req.origin,
            "tender_quote": req.tender_quote,
            "conclusion": "缺失",
            "reason": "未检索到可用于核验该要求的应标证据。",
            "source": "无",
            "citations": [],
            "retrieved_evidence_ids": [],
            "citation_valid": True,
            "ungrounded_citation_ids": [],
            "deterministic_rule": {
                "status": "not_applicable",
                "reason": "没有可用于规则校验的响应证据。",
            },
        }

    prompt = f"""你是 IDC 应标书审核专家。判断应标书在【{req.dimension}】这一项是否达标。

审核项：{req.requirement_id}
要求来源：{"招标文件" if req.origin == "tender" else "行业基准"}
招标原文：{req.tender_quote or "（无，使用行业基准）"}
达标标准(expect)：{req.expected}

从应标书中检索到的相关内容（这是你唯一能依据的原文）：
---
{evidence_text}
---

⚠️ 铁律（防幻觉）：
1. 只依据上面检索到的原文判断，【严禁】编造原文里没有的信息、数值、承诺。
2. 若原文里根本没提到这项 → conclusion 判"缺失"、reason 写"检索内容中未提及"，不要臆测达标。
3. 原文提到但不满足标准 → 判"风险"；明确满足 → 判"达标"。
4. citations 只能填写上文方括号中的 evidence_id，并给出对应原文短句。
5. 事实、数值和结论必须能被 citations 支撑；不能用招标要求冒充应标响应。"""

    llm = _get_llm()
    r = llm.invoke(prompt)
    valid_citations, invalid_ids = [], []
    for citation in r.citations:
        body = evidence_by_id.get(citation.evidence_id)
        quote = citation.quote.replace("…", "").replace("...", "").strip()
        if body is not None and (not quote or quote[:15] in body):
            valid_citations.append(citation.model_dump())
        else:
            invalid_ids.append(citation.evidence_id)

    citation_valid = not invalid_ids and (
        r.conclusion == "缺失" or bool(valid_citations)
    )
    cited_text = "\n".join(citation["quote"] for citation in valid_citations)
    deterministic_rule = evaluate_numeric_requirement(req.expected, cited_text)
    conclusion = r.conclusion
    reason = r.reason
    if citation_valid and deterministic_rule["status"] == "fail":
        conclusion = "风险"
        reason = f"{r.reason} {deterministic_rule['reason']}"
    source = valid_citations[0]["evidence_id"] if valid_citations else "无"
    return {
        "id": req.requirement_id,
        "dimension": req.dimension,
        "level": req.level,
        "mandatory": req.mandatory,
        "requirement_origin": req.origin,
        "tender_quote": req.tender_quote,
        "conclusion": conclusion,
        "reason": reason,
        "source": source,
        "citations": valid_citations,
        "retrieved_evidence_ids": list(evidence_by_id),
        "citation_valid": citation_valid,
        "ungrounded_citation_ids": invalid_ids,
        "deterministic_rule": deterministic_rule,
    }


def load_checklist():
    return yaml.safe_load(open(_CHECKLIST, encoding="utf-8"))


def audit_all(only_id=None, items=None, vs=None, output_path=None):
    """跑全部（或单项）checklist，返回审核结果列表。"""
    items = items or load_checklist()
    if only_id:
        items = [x for x in items if _normalize_item(x).requirement_id == only_id]
    vs = vs or load_index()  # 加载一次向量库，复用
    results = []
    for it in items:
        req = _normalize_item(it)
        print(f"审核 [{req.requirement_id}] {req.dimension} ...", flush=True)
        results.append(audit_one(it, vs=vs))
    # 存 JSON 供报告生成器(report.py)读取
    import json
    out = output_path or os.path.join(_ROOT, "data", "audit_result.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[OK] 审核结果 -> {out}")
    return results


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows GBK 终端防 UnicodeEncodeError
    only = sys.argv[1] if len(sys.argv) > 1 else None
    res = audit_all(only_id=only)
    print("\n" + "=" * 60)
    icon = {"达标": "✅", "缺失": "❌", "风险": "⚠️"}
    for r in res:
        print(f"{icon.get(r['conclusion'],'?')} [{r['level']}] {r['id']}({r['dimension']}): {r['conclusion']}")
        print(f"    理由: {r['reason'][:80]}")
        print(f"    出处: {r['source'][:50]}")
