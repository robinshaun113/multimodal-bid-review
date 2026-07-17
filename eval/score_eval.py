"""
eval/score_eval.py — 评估打分 (Day45 评估二·闭环)

读 expert_labels.csv (专家填好 expert_conclusion 列) + AI 结论，算：
  一致率 / 漏检率 / 误检率，并列出每个不一致项。

术语(审核语境):
  漏检(最危险) = 实际有问题(专家判缺失/风险)，AI 却判达标 → 放过废标风险
  误检(可容忍) = 实际没问题(专家判达标)，AI 判缺失/风险 → 虚报，增人工成本
用法：先填 expert_labels.csv 的 expert_conclusion 列，再 python eval/score_eval.py
"""
import os
import sys
import csv

_LABELS = os.path.join(os.path.dirname(__file__), "expert_labels.csv")

_OK = "达标"
_BAD = ("缺失", "风险")   # 视为"有问题/需关注"


def score():
    rows = list(csv.DictReader(open(_LABELS, encoding="utf-8-sig")))
    filled = [r for r in rows if r["expert_conclusion"].strip()]
    if not filled:
        print("expert_labels.csv 的 expert_conclusion 列还没填，先填完再跑。")
        print("每格填：达标 / 缺失 / 风险")
        return

    n = len(filled)
    agree = miss = false_alarm = 0
    diffs = []
    for r in filled:
        ai, exp = r["ai_conclusion"].strip(), r["expert_conclusion"].strip()
        if ai == exp:
            agree += 1
            continue
        # 不一致：判方向
        if exp in _BAD and ai == _OK:
            kind = "漏检‼️(实际有问题,AI说达标)"
            miss += 1
        elif exp == _OK and ai in _BAD:
            kind = "误检(实际达标,AI虚报)"
            false_alarm += 1
        else:
            kind = "程度不一致(缺失↔风险)"
        diffs.append((r["id"], ai, exp, kind))

    print(f"已填 {n}/12 项")
    print(f"一致率  : {agree}/{n} = {agree/n:.0%}")
    print(f"漏检率  : {miss}/{n} = {miss/n:.0%}  (审核最怕这个)")
    print(f"误检率  : {false_alarm}/{n} = {false_alarm/n:.0%}")
    if diffs:
        print("\n不一致明细：")
        for rid, ai, exp, kind in diffs:
            print(f"  - {rid}: AI={ai} vs 专家={exp} → {kind}")
    else:
        print("\n全部一致。样本小(12项)，仅作方法论验证，勿宣称统计意义。")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    score()
