"""
src/report.py — 审核报告生成器 (Day43)

把审核结果渲染成"评标人一眼抓重点"的 Markdown 报告：
  ① 结论摘要钉顶（统计 + 废标红线不合格数=最要命的数字）
  ② 废标红线 优先于 技术展示
  ③ 每组内：不合格(缺失/风险) 顶前，达标 沉底

用法：python src/report.py   # 读 data/audit_result.json 生成报告
"""
import os
import sys
import json

from jinja2 import Template

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_RESULT_JSON = os.path.join(_ROOT, "data", "audit_result.json")
_REPORT_MD = os.path.join(_ROOT, "data", "audit_report.md")

# 排序权重：结论(不合格优先) + level(废标红线优先)
_CONCLUSION_ORDER = {"缺失": 0, "风险": 1, "达标": 2}
_LEVEL_ORDER = {"废标红线": 0, "技术展示": 1, "次要": 2}

_TEMPLATE = """# 应标书审核报告

> 自动生成 · 仅供参考，最终以人工复核为准。数据为方法论验证样本（小批）。

## 一、结论摘要

- 审核项：**{{ total }}** 项 | ✅达标 {{ n_pass }} | ❌缺失 {{ n_miss }} | ⚠️风险 {{ n_risk }}
- 🔴 **废标红线里不合格：{{ n_redline_bad }} 项**{% if n_redline_bad > 0 %}（需重点关注，可能影响标书有效性）{% else %}（红线项均达标）{% endif %}

{% for g in groups %}## 二、{{ g.title }}
{% for r in g.rows %}
### {{ r.icon }} {{ r.dimension }}（{{ r.id }}） — **{{ r.conclusion }}**
- **理由**：{{ r.reason }}
- **出处**：{{ r.source }}
{% endfor %}
{% endfor %}"""


def _sort_key(r):
    return (_LEVEL_ORDER.get(r["level"], 9), _CONCLUSION_ORDER.get(r["conclusion"], 9))


def render_report(results):
    """results: audit_all 的结果列表。返回 Markdown 字符串。"""
    icon = {"达标": "✅", "缺失": "❌", "风险": "⚠️"}
    for r in results:
        r["icon"] = icon.get(r["conclusion"], "?")
    ordered = sorted(results, key=_sort_key)

    # 按 level 分组（废标红线在前）
    groups = []
    for lv in ["废标红线", "技术展示", "次要"]:
        rows = [r for r in ordered if r["level"] == lv]
        if rows:
            groups.append({"title": lv, "rows": rows})

    n_redline_bad = sum(1 for r in results
                        if r["level"] == "废标红线" and r["conclusion"] in ("缺失", "风险"))
    md = Template(_TEMPLATE).render(
        total=len(results),
        n_pass=sum(1 for r in results if r["conclusion"] == "达标"),
        n_miss=sum(1 for r in results if r["conclusion"] == "缺失"),
        n_risk=sum(1 for r in results if r["conclusion"] == "风险"),
        n_redline_bad=n_redline_bad,
        groups=groups,
    )
    return md


if __name__ == "__main__":
    if not os.path.exists(_RESULT_JSON):
        print(f"未找到 {_RESULT_JSON}，请先跑 audit_agent 生成结果 JSON"); sys.exit(1)
    results = json.load(open(_RESULT_JSON, encoding="utf-8"))
    md = render_report(results)
    open(_REPORT_MD, "w", encoding="utf-8").write(md)
    print(f"✓ 报告已生成 → {_REPORT_MD}\n" + "=" * 50)
    print(md[:800])
