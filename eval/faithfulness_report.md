# 历史忠实度基线（旧口径，已停止作为简历指标）

> 该报告使用旧版“引用短句是否存在于整个知识库”口径，不能证明引用属于当次
> 检索窗口，也不能证明零幻觉。新版评估器已改为 evidence_id 窗口级校验；
> 需在新版 pipeline 重新运行后生成新报告。

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

**历史结果**：12/12 项短引用可在全库找到。该数字仅作为迁移前基线，不再对外表述为“0 幻觉”。

> 局限：本轴只证'没编造出处'，**不等于判断正确**。真实漏检/误检率需招标方专家读整份标书比对，样本 1 份不宣称统计意义。
