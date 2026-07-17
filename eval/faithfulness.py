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
import json

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_RESULT = os.path.join(_ROOT, "data", "audit_result.json")
_OUT = os.path.join(os.path.dirname(__file__), "faithfulness_report.md")


def check():
    results = {x["id"]: x for x in json.load(open(_RESULT, encoding="utf-8"))}
    rows, grounded, honest, bad = [], 0, 0, 0
    for cid, r in results.items():
        cited = {c["evidence_id"] for c in r.get("citations", [])}
        retrieved = set(r.get("retrieved_evidence_ids", []))
        invalid = cited - retrieved
        if invalid or not r.get("citation_valid", False):
            tag = "UNGROUNDED‼️"
            bad += 1
        elif cited:
            tag = "grounded-in-run"
            grounded += 1
        elif r["conclusion"] == "缺失":
            tag = "no-ev-honest"
            honest += 1
        else:
            tag = "no-src?"
            bad += 1
        rows.append((cid, r["conclusion"], tag))

    n = len(rows)
    lines = ["# Day45 忠实度检查（全自动，抗幻觉）\n",
             f"> 样本：1 份标书 × {n} 项。验证引用是否来自该项实际证据窗口，不判审核对错。\n",
             "| 审核项 | 结论 | 出处是否有据 |", "|---|---|---|"]
    for cid, c, tag in rows:
        lines.append(f"| {cid} | {c} | {tag} |")
    lines += [
        "\n## 汇总",
        f"- 当次证据窗口内有据(grounded-in-run)：{grounded}/{n}",
        f"- 诚实判缺失(source=无+结论缺失)：{honest}/{n}",
        f"- 疑似幻觉(UNGROUNDED)：{bad}/{n}",
        f"\n**结论**：{grounded + honest}/{n} 项引用受当次检索证据约束或诚实空缺，"
        f"未溯源引用 {bad} 项。",
        "\n> 局限：本轴只证'引用没有越出当次证据窗口'，**不等于判断正确，也不等于零幻觉**。"
        "真实漏检/误检率需招标方专家读整份标书比对，样本 1 份不宣称统计意义。",
    ]
    open(_OUT, "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines[4:]))   # 控制台只打表体+汇总
    print(f"\n[OK] -> {_OUT}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    check()
