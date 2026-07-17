"""
eval/faithfulness.py — 忠实度/抗幻觉检查 (Day45 评估三·全自动)

不判"对错"(那要专家读整份标书)，只验一件 AI 审核系统必须过关的事：
  AI 给的"出处"是不是真的来自检索到的原文？还是模型编的？
纯字符串匹配，无 LLM 调用，快且便宜。

分类：
  grounded      = source 能在该项的检索证据里找到 → 有据，没编
  no-ev-honest  = source=无 且 结论=缺失 → 诚实承认没检索到，符合防幻觉铁律
  UNGROUNDED    = source 在证据里找不到 → 可能幻觉，红旗
用法：python eval/faithfulness.py
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from multimodal_rag import query, load_index
from audit_agent import load_checklist

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_RESULT = os.path.join(_ROOT, "data", "audit_result.json")
_OUT = os.path.join(os.path.dirname(__file__), "faithfulness_report.md")


def check():
    import chromadb
    results = {x["id"]: x for x in json.load(open(_RESULT, encoding="utf-8"))}
    # 抗幻觉正确定义：AI引的出处是否在【整个知识库】里真实存在(不是某次检索窗口)
    col = chromadb.PersistentClient(
        path=os.path.join(_ROOT, "data", "chroma_db")).get_collection("bid_multimodal")
    allc = col.get(include=["documents", "metadatas"])
    all_text = "\n".join(allc["documents"])
    all_rids = {(m or {}).get("rid") for m in allc["metadatas"]
                if (m or {}).get("type") == "image"}

    rows, grounded, honest, bad = [], 0, 0, 0
    for cid, r in results.items():
        src = (r.get("source") or "").strip()
        if src in ("", "无"):
            tag = "no-ev-honest" if r["conclusion"] == "缺失" else "no-src?"
            if tag == "no-ev-honest":
                honest += 1
        elif src.startswith("[图"):
            rid = src[2:].strip("] ").split()[0]
            tag, cnt = ("grounded", 1) if rid in all_rids else ("UNGROUNDED‼️", 0)
            grounded += cnt; bad += (1 - cnt)
        else:
            body = src.split("]", 1)[-1].strip() if src.startswith("[") else src
            body = body.replace("…", "").replace("...", "").strip()  # LLM引用常带省略号
            anchor = body[:15]
            tag, cnt = ("grounded", 1) if anchor and anchor in all_text else ("UNGROUNDED‼️", 0)
            grounded += cnt; bad += (1 - cnt)
        rows.append((cid, r["conclusion"], tag))

    n = len(rows)
    lines = ["# Day45 忠实度检查（全自动，抗幻觉）\n",
             f"> 样本：1 份标书 × {n} 项。只验'出处是否真实检索所得'，不判对错。\n",
             "| 审核项 | 结论 | 出处是否有据 |", "|---|---|---|"]
    for cid, c, tag in rows:
        lines.append(f"| {cid} | {c} | {tag} |")
    lines += [
        "\n## 汇总",
        f"- 有据(grounded)：{grounded}/{n}",
        f"- 诚实判缺失(source=无+结论缺失)：{honest}/{n}",
        f"- 疑似幻觉(UNGROUNDED)：{bad}/{n}",
        f"\n**结论**：{grounded + honest}/{n} 项出处可追溯或诚实空缺，"
        f"疑似幻觉 {bad} 项。防幻觉铁律{'通过' if bad == 0 else '有漏，需查'}。",
        "\n> 局限：本轴只证'没编造出处'，**不等于判断正确**。"
        "真实漏检/误检率需招标方专家读整份标书比对，样本 1 份不宣称统计意义。",
    ]
    open(_OUT, "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines[4:]))   # 控制台只打表体+汇总
    print(f"\n[OK] -> {_OUT}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    check()
