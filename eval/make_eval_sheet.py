"""
eval/make_eval_sheet.py — 生成人工评估工作表 (Day45 评估二)

P3 是"审核"任务，没有现成 gold answer——真正的漏检/误检要拿 AI 结论去比对
【标书里每项的真实情况】，而那个基准是领域专家(填过偏离表的人)，不是 AI 自己。
所以本脚本只做能自动的部分，把需要人判断的留成空列：

  每项输出：维度 | AI结论 | AI理由 | AI出处 | 召回诊断 | [空]专家结论 | [空]AI对否 | [空]漏检/误检
  专家填完空列后，可跑 score_eval.py 算一致率 / 漏检率 / 误检率。

诚实标注：样本量 = 1 份 docx 应标书 × 12 项 checklist（小样本，方法论验证级）。
用法：python eval/make_eval_sheet.py  →  写 eval/eval_sheet.md
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from recall_probe import probe

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_RESULT = os.path.join(_ROOT, "data", "audit_result.json")
_OUT = os.path.join(os.path.dirname(__file__), "eval_sheet.md")


def main():
    results = json.load(open(_RESULT, encoding="utf-8"))
    # 跑召回诊断，拿到哪些项有缺口
    print("--- 跑召回诊断 ---")
    gaps = {g["id"]: g["n_missed"] for g in probe()}

    lines = []
    lines.append("# P3 应标书审核 · 人工评估工作表 (Day45)\n")
    lines.append("> **数据来源**：1 份真实 IDC 应标技术标书 (docx，本地脱敏)｜"
                 "**样本量**：12 项 checklist（小样本，方法论验证级，非统计显著）\n")
    lines.append("> **AI 侧**：全量文本 3236 块 + 抽样 60 张图 (VLM 读图) 入库，"
                 "audit k=8 + 按维度定向检索\n")
    lines.append("> **怎么用**：本表是**阅读材料**——逐项读 AI 结论/理由/出处，对照你对标书的"
                 "真实理解做判断；把你的结论填进**答题卡** `eval/expert_labels.csv` 的 "
                 "expert_conclusion 列（达标/缺失/风险），填完跑 `python eval/score_eval.py`。\n")
    lines.append("\n## 一、逐项对比\n")

    for r in results:
        rid = r["id"]
        gap = gaps.get(rid, 0)
        gap_note = f"⚠️深捞k=25 还有 {gap} 条含关键信号证据未进 k=8 窗口" if gap else "✓k=8 窗口已覆盖"
        lines.append(f"### [{r['conclusion']}] {rid} — {r['dimension']} ({r['level']})\n")
        lines.append(f"- **AI 结论**：{r['conclusion']}")
        lines.append(f"- **AI 理由**：{r['reason']}")
        lines.append(f"- **AI 出处**：{r.get('source') or '无'}")
        lines.append(f"- **召回诊断**：{gap_note}")
        lines.append(f"- **→ 你的判断**：在 expert_labels.csv 里给 `{rid}` "
                     f"填 达标/缺失/风险\n")

    lines.append("\n## 二、召回诊断小结（自动）\n")
    lines.append(f"- 12 项中 **{len(gaps)} 项**在 audit 的 k=8 窗口外仍有含关键信号的证据。")
    lines.append("- **含义**：缺口≠判错；但对判'风险/缺失'的项，缺口是高危复核点"
                 "（可能因窗口漏证据而偏保守）。")
    lines.append("- **高危复核点**（有缺口 且 AI 判风险/缺失）：")
    for r in results:
        if r["conclusion"] in ("风险", "缺失") and gaps.get(r["id"], 0) > 0:
            lines.append(f"    - {r['id']} ({r['conclusion']}): 深捞 {gaps[r['id']]} 条未进窗口，重点核")

    lines.append("\n## 三、填完后算什么指标\n")
    lines.append("- **一致率** = AI 判对项数 / 12")
    lines.append("- **漏检率** = 漏检项数 / 12（审核最怕漏检——把废标风险说成没问题）")
    lines.append("- **误检率** = 误检项数 / 12（误检=虚报，增加人工复核成本但不致命）")
    lines.append("- 诚实结论模板：'在 1 份标书 12 项上，一致 X 项，漏检 Y 项（均在___维度），"
                 "根因___'。样本小，只作方法论验证，不宣称统计意义。\n")

    open(_OUT, "w", encoding="utf-8").write("\n".join(lines))
    print(f"\n[OK] 评估工作表 -> {_OUT}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
