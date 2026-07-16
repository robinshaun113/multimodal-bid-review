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
import glob

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

sys.path.insert(0, os.path.dirname(__file__))
from multimodal_rag import query, load_index

load_dotenv(override=True)

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_CHECKLIST = os.path.join(_ROOT, "checklist.yaml")


class AuditResult(BaseModel):
    """单项审核结论（结构化，防止 LLM 自由发挥）"""
    conclusion: str = Field(description="必须是三者之一：达标 / 缺失 / 风险")
    reason: str = Field(description="判断理由，必须引用检索到的原文片段；原文没提到就说'检索内容中未提及'")
    source: str = Field(description="依据来自哪：文本片段前20字 或 图片rid；无依据填'无'")


def _get_llm():
    return ChatOpenAI(
        model="qwen3-max",
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0,
    ).with_structured_output(AuditResult, method="function_calling")


def audit_one(item, vs=None, k=4):
    """审一项：检索 → LLM 对照 expect 判断（防幻觉）。返回 dict。"""
    hits = query(item["query"], k=k, vs=vs)
    # 把检索到的证据(文本内容 / 图描述)拼成上下文
    evidence = []
    for h in hits:
        if h["type"] == "image":
            evidence.append(f"[图 {h['rid']}] {h['desc']}")
        else:
            evidence.append(f"[文本] {h['content']}")
    evidence_text = "\n".join(evidence) if evidence else "（未检索到相关内容）"

    prompt = f"""你是 IDC 应标书审核专家。判断应标书在【{item['dimension']}】这一项是否达标。

审核项：{item['id']}
达标标准(expect)：{item['expect']}

从应标书中检索到的相关内容（这是你唯一能依据的原文）：
---
{evidence_text}
---

⚠️ 铁律（防幻觉）：
1. 只依据上面检索到的原文判断，【严禁】编造原文里没有的信息、数值、承诺。
2. 若原文里根本没提到这项 → conclusion 判"缺失"、reason 写"检索内容中未提及"，不要臆测达标。
3. 原文提到但不满足标准 → 判"风险"；明确满足 → 判"达标"。
4. reason 必须引用原文具体片段，source 标明来自哪段文本或哪张图。"""

    llm = _get_llm()
    r = llm.invoke(prompt)
    return {
        "id": item["id"], "dimension": item["dimension"], "level": item["level"],
        "conclusion": r.conclusion, "reason": r.reason, "source": r.source,
    }


def load_checklist():
    return yaml.safe_load(open(_CHECKLIST, encoding="utf-8"))


def audit_all(only_id=None):
    """跑全部（或单项）checklist，返回审核结果列表。"""
    items = load_checklist()
    if only_id:
        items = [x for x in items if x["id"] == only_id]
    vs = load_index()  # 加载一次向量库，复用
    results = []
    for it in items:
        print(f"审核 [{it['id']}] {it['dimension']} ...", flush=True)
        results.append(audit_one(it, vs=vs))
    # 存 JSON 供报告生成器(report.py)读取
    import json
    out = os.path.join(_ROOT, "data", "audit_result.json")
    json.dump(results, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"✓ 审核结果 → {out}")
    return results


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    res = audit_all(only_id=only)
    print("\n" + "=" * 60)
    icon = {"达标": "✅", "缺失": "❌", "风险": "⚠️"}
    for r in res:
        print(f"{icon.get(r['conclusion'],'?')} [{r['level']}] {r['id']}({r['dimension']}): {r['conclusion']}")
        print(f"    理由: {r['reason'][:80]}")
        print(f"    出处: {r['source'][:50]}")
