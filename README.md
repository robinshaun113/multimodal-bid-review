# 多模态 IDC 招投标合规审核

> 面向 AI 解决方案工程师作品集的端到端项目：从招标文件抽取强制要求，
> 在应标文件的文本、表格和图片中寻找证据，输出可追溯的需求—响应合规矩阵。

## 业务问题

IDC 招投标审核不是“总结一份文档”，而是同时回答三个问题：

1. 招标方究竟要求了什么，哪些是★/▲/必须项？
2. 应标方在哪里作出了响应，文本、表格和拓扑图是否一致？
3. 哪些判断可以自动完成，哪些废标风险必须由人确认？

系统因此支持两种模式：

- **招标—应标对照**：上传两份 DOCX，从招标文件动态抽取要求并核对应标证据。
- **行业基准扫描**：只上传应标文件，使用 `checklist.yaml` 做风险预检。

## 架构

```text
招标 DOCX ─→ 保序解析 ─→ 需求抽取 ───────────────┐
                                                 ├─→ Requirement × Evidence 合规矩阵
应标 DOCX ─→ 文本/表格/图片解析 ─→ 证据索引 ─────┘          │
                                                             ↓
                                  LangGraph 并行审核 → 引用校验 → HITL → 报告
```

核心设计：

- **文档结构**：保留段落/表格阅读顺序、标题章节、block index 和图片 OOXML 锚点。
- **证据契约**：每个文本块和图片拥有稳定 `evidence_id`；LLM 只能引用本次检索窗口中的 ID。
- **混合判定**：LLM 负责语义理解；代码对“≥99.99%”“≤30 分钟”等唯一数值阈值做保守复核，歧义场景不强判。
- **双文档审核**：要求来源于招标文件；静态 Checklist 仅作为无招标文件时的基准。
- **可靠执行**：LangGraph `Send` 并行审核要求，节点重试；废标红线可通过 `interrupt()` 人工确认。
- **数据隔离**：应标文件按内容哈希使用独立 Chroma collection，避免不同用户互相污染。

## 当前技术栈

- LangChain / LangGraph 1.2 / Pydantic structured output
- Chroma 文本证据索引
- Qwen3.7-Plus：招标需求抽取与合规判断
- qwen-vl-max：图片描述基线
- `qwen3-vl-embedding`：原生以文搜图实验轨道，独立评测后再决定是否默认融合
- python-docx / OOXML relationship / Gradio / Docker

## 为什么不是“所有新技术都默认开启”

当前图片主链路仍保留“VLM 描述 → 文本向量”基线，同时新增
`src/native_multimodal.py` 作为原生跨模态检索实验轨道。只有在图片 Recall@K
证明有收益后，才将其与文本检索融合。GraphRAG、Agent Swarm 和更换向量数据库
不解决当前核心问题，因此不为技术标签引入。

## 评测设计

评测分四层，避免用一个“准确率”掩盖不同错误：

| 层 | 指标 |
|---|---|
| 需求抽取 | 强制项召回率、阈值/单位抽取正确率 |
| 证据检索 | 文本 Recall@K、图片 Recall@K |
| 合规判断 | 废标风险召回率、漏检率、误报率 |
| 引用可信 | citation 是否属于该次检索窗口、quote 是否命中对应 evidence |

旧版“12/12、0 幻觉”只能说明短引用在全库存在，已停止作为简历结论。新版
`eval/faithfulness.py` 验证引用是否属于**该审核项实际看到的证据窗口**，但仍明确：
引用可追溯不等于判断正确。

建议公开评测使用脱敏变体：删除 SLA、修改 PUE、取消 N+1、移除拓扑图等，
构造有明确 gold label 的 Requirement × Document 数据集。

## 运行

```bash
pip install -r requirements.txt
copy .env.example .env
python app.py
```

打开 `http://localhost:7860`，上传招标文件（可选）和应标文件。

```bash
docker build -t bid-review .
docker run -p 7860:7860 -e DASHSCOPE_API_KEY=sk-xxx bid-review
```

## 数据与安全边界

- 原始文件、解析图片、向量库和审核产物均被 `.gitignore` 排除。
- 文件与产物保存在本地，但选定文本和图片会发送到百炼云端 API 推理。
- 敏感标书应先脱敏，或将模型接口替换为企业私有化部署。
- Gradio 页面无鉴权，仅用于本机或可信内网演示。

## 目录

```text
src/
  docx_parser.py           保序 DOCX/表格/图片锚点解析
  requirement_extractor.py 招标要求结构化抽取
  schemas.py               Requirement/Evidence/Citation 契约
  multimodal_rag.py        文本+图片描述证据索引
  native_multimodal.py     qwen3-vl-embedding 原生以文搜图实验
  audit_agent.py           单项合规判断与窗口级引用校验
  rules.py                 SLA/比例/时长等确定性数值复核
  review_workflow.py       LangGraph 并行、重试、HITL
  report.py                合规矩阵报告
tests/                     无模型调用的契约和流程测试
eval/                      召回、引用、人工标签评测
```

## 已知边界

- DOCX 是流式排版格式，可靠页码需要先渲染为 PDF，再接布局解析/OCR。
- EMF/WMF 仍需转换为 PNG；当前解析器会保留其锚点，但 VLM 不直接读取。
- 原生多模态索引已具备代码路径，尚需公开图片 gold set 证明收益。
- 招标需求抽取和最终合规准确率仍需脱敏数据集与人工复核扩充。
