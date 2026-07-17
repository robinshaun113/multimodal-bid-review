# P3 · 多模态 IDC 招投标合规审核｜设计文档

## 1. 场景

IDC 技术标书包含 SLA、机房等级、供电冗余、技术偏离表、拓扑图和机柜布局图等
图文混合信息。人工审核需要先从招标文件整理要求，再到应标文件中逐项寻找响应，
工作量大，也容易遗漏强制项和数值阈值。

本项目将问题拆成两个独立对象：

- **Requirement**：招标文件中的要求、阈值、强制等级和原文；
- **Evidence**：应标文件中的文本、表格或图片证据。

系统输出 Requirement × Evidence 合规矩阵，而不是只对一份文件做摘要。

## 2. 使用模式

1. **招标—应标对照**：上传两份 DOCX，动态抽取招标要求并核对应标证据；
2. **行业基准扫描**：只上传应标文件，使用 `checklist.yaml` 做预检。

## 3. 处理流程

```text
招标 DOCX → 保序解析 → 结构化需求抽取 ───────────┐
                                                 ├→ 并行合规审核 → 引用校验 → 报告
应标 DOCX → 文本/表格/图片解析 → 证据索引 ──────┘                         │
                                                                         └→ 人工复核
```

### 文档解析

- 按原始阅读顺序解析段落和表格；
- 保存标题章节和 `block_index`；
- 从 OOXML relationship 中记录图片锚点和所属章节；
- 以文件内容哈希生成 `document_id`。

### 需求抽取

Qwen 通过结构化输出生成 `Requirement`，代码负责：

- 校验 `source_quote` 必须存在于对应招标块；
- 为要求和招标证据生成稳定 ID；
- 去重并限制最大要求数量；
- 保留强制项、阈值、单位和来源章节。

### 应标证据索引

- 文本和完整表格块进入 Chroma；
- 图片主链路采用 qwen-vl-max 描述后进入文本向量库；
- 每份应标文件使用独立 collection，避免跨文档串库；
- `qwen3-vl-embedding` 原生以文搜图保留为单独实验轨道。

### 合规判断

- LangGraph `Send` 并行处理每条 Requirement；
- 节点失败按 RetryPolicy 重试；
- LLM 只能引用本次检索窗口中的 `evidence_id`；
- 引用短句必须命中对应证据；
- 对唯一、明确的数值阈值使用代码二次复核；
- 强制项风险可通过 `interrupt()` 交给人工确认。

## 4. 核心数据结构

```text
Requirement
  requirement_id / dimension / expected / mandatory
  tender_evidence_id / tender_quote / tender_section

Evidence
  evidence_id / document_id / type / source
  section / block_index / content

AuditDecision
  conclusion / reason / citations / deterministic_rule
```

## 5. 技术选型

- 编排：LangGraph
- LLM 与结构化输出：LangChain、Qwen3.7-Plus、Pydantic
- 图片理解：qwen-vl-max
- 原生多模态实验：qwen3-vl-embedding
- 向量库：Chroma
- 文档：python-docx + OOXML
- 报告与界面：Jinja2、Gradio

## 6. 评测

评测拆为四层：

- 需求抽取：强制项召回、阈值和单位正确率；
- 证据检索：文本 Recall@K、图片 Recall@K；
- 合规判断：废标风险召回、漏检和误报；
- 引用约束：citation 是否属于当前检索窗口，quote 是否命中对应 evidence。

引用可追溯不等于判断正确。最终准确率需要领域专家标注 Requirement × Document
数据集，因此当前仓库不将单份样本结果解释为生产指标。

## 7. 安全边界

- 原始文件、图片、向量库和报告不提交到 Git；
- 选中的文本和图片会发送到百炼云端 API；
- 敏感标书应先脱敏，或替换为企业私有化模型；
- Gradio 页面只用于本机或可信内网演示，未内置鉴权。
