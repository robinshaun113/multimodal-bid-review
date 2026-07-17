# Day45 忠实度检查（全自动，抗幻觉）

> 样本：1 份标书 × 12 项。只验'出处是否真实检索所得'，不判对错。

| 审核项 | 结论 | 出处是否有据 |
|---|---|---|
| mandatory_response | 风险 | grounded |
| room_grade | 达标 | grounded |
| sla_availability | 达标 | grounded |
| rack_power_density | 达标 | grounded |
| pue | 风险 | grounded |
| power_redundancy | 风险 | grounded |
| cooling | 风险 | grounded |
| ops_response | 风险 | grounded |
| topology_diagram | 风险 | grounded |
| rack_layout_diagram | 达标 | grounded |
| price_reasonableness | 风险 | grounded |
| penalty_clause | 达标 | grounded |

## 汇总
- 有据(grounded)：12/12
- 诚实判缺失(source=无+结论缺失)：0/12
- 疑似幻觉(UNGROUNDED)：0/12

**结论**：12/12 项出处可追溯或诚实空缺，疑似幻觉 0 项。防幻觉铁律通过。

> 局限：本轴只证'没编造出处'，**不等于判断正确**。真实漏检/误检率需招标方专家读整份标书比对，样本 1 份不宣称统计意义。