"""
eval/recall_probe.py — 检索召回诊断 (Day45 评估一)

背景：Day46 挖出四层"假缺失"，都是检索/数据管道问题。修完后要回答一个问题——
      "audit 用的 k=8 检索，还有没有漏掉库里真实存在的关键证据？"

方法（不需要人工标注，纯自动）：
  对每个 checklist 项：
    A = audit_one 实际用的检索(query, k=8, 按维度过滤)命中的证据
    B = 同 query 深捞(k=25)命中的证据
    diff = B 有、A 没有、且含"关键信号"(数值/百分比/N+1/冗余/等级)的证据
  diff 非空 = audit 的窗口可能漏掉了实质证据 → 潜在召回缺口，人工复核点。

这不判对错(对错要专家填)，只量化"检索层还剩多少盲区"，是数据管道体检。
用法：python eval/recall_probe.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from multimodal_rag import query, load_index
from audit_agent import load_checklist

# "关键信号"正则：审核真正在意的硬内容(数字/冗余/等级/承诺词)
_SIGNAL = re.compile(
    r"(\d+\.?\d*\s*%|\d+\.?\d*\s*(kW|小时|分钟|年)|N\+1|2N|9{2,}(\.\d+)?%?"
    r"|冗余|Tier|A级|GB\s?50174|SLA|可用性|业务连续性|违约|赔偿|罚)"
)

_AUDIT_K = 8
_DEEP_K = 25


def _texts(hits):
    """把检索结果统一成文本列表(去掉图，图纸维度另算)。"""
    out = []
    for h in hits:
        c = h.get("content") or h.get("desc") or ""
        out.append(c.strip())
    return out


def probe():
    vs = load_index()
    checklist = load_checklist()
    gaps = []
    for item in checklist:
        is_diagram = "图纸" in item["dimension"]
        only_type = None if is_diagram else "text"
        q = item["query"]

        shallow = set(_texts(query(q, k=_AUDIT_K, vs=vs, only_type=only_type)))
        deep = _texts(query(q, k=_DEEP_K, vs=vs, only_type=only_type))

        # deep 里有、shallow 里没有、且含关键信号的 → 潜在漏检证据
        missed = [t for t in deep if t not in shallow and _SIGNAL.search(t)]
        status = "⚠️ 有缺口" if missed else "✓ 无缺口"
        print(f"{status} [{item['id']}] ({item['dimension']})")
        if missed:
            for m in missed[:3]:
                print(f"    深捞才现: {m[:70]}")
            gaps.append({"id": item["id"], "n_missed": len(missed),
                         "samples": missed[:3]})
    print("=" * 60)
    print(f"12 项中 {len(gaps)} 项在 k={_AUDIT_K} 窗口外仍有含关键信号的证据。")
    print("解读：缺口≠判错(专家复核才定漏检)，但缺口多说明 k 或 query 仍可优化。")
    return gaps


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    probe()
