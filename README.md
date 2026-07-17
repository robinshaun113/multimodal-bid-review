# 多模态 IDC 应标技术标书智能审核

> VLM 读图（拓扑/机柜布局）+ docx 解析 + 多模态 RAG，按 checklist 审核应标书的响应完整性与技术达标性。

## 为什么做这个

在中国移动 IDC 实习期间，我做过一项重复且吃业务经验的活：拿着招标要求逐条核对应标技术标书——机房等级够不够 A 级、SLA 有没有承诺到 99.9%、供电是不是 N+1 冗余、偏离表有没有逐条正面响应。一份标书几百页、几百张图（拓扑图、机柜布局图），人工审既慢又容易漏。

应标书天生**图多**（乙方要秀方案，含大量拓扑/机柜布局图），这正是纯文本 RAG 接不住、必须上多模态的场景——**图是这个项目的灵魂**。

## 它做什么

上传一份 `.docx` 应标技术标书，系统自动跑完五环 pipeline，产出一份分维度的审核报告（废标红线优先、不合格项钉顶）。

```
docx 应标书
   │
   ├─① docx 解析      python-docx 抽文本(段落+表格) + 解压 word/media 取内嵌图
   │
   ├─② 多模态入库      文本 → embedding 直接入库
   │                  图  → VLM(qwen-vl-max) 读成文字描述 → embedding 入库(metadata 拴原图)
   │
   ├─③ 逐项检索        每条 checklist 用 query 去向量库检索；按维度定向(文本项只检文本)
   │
   ├─④ 审核 Agent      检索证据 + expect 标准 → LLM 判 达标/风险/缺失（防幻觉：只依据原文）
   │
   └─⑤ 报告生成        Jinja2 渲染，结论摘要钉顶 + 废标红线优先
```

## 技术栈

- **VLM**：qwen-vl-max（读拓扑/机柜/证书图 → 结构化描述）
- **Embedding / LLM**：text-embedding-v2 / qwen3-max（DashScope）
- **向量库**：Chroma（文本 + 图描述统一入库，type 字段区分）
- **解析 / 图像**：python-docx、Pillow（超大图压缩）
- **前端 / 部署**：Gradio、Docker

## 这个项目最值钱的部分：一次真实的排雷

第一版审核报告显示「12 项废标红线里 9 项缺失」——一份真实中标级标书不可能全崩。顺着证据挖，挖出**四层"假缺失"**，每层都是不同的检索/数据管道问题：

| 层 | 表象 | 根因 | 修复 |
|---|---|---|---|
| ① | 9 项缺失 | 库只入了 25 条测试样本，真实标书 4011 文本块没进库 | 全量文本入库（分批绕过 batch 上限） |
| ② | 仍 5 项缺失 | k=4 太小，标题/表头碎片挤占检索窗口，实质内容被挤出 | k=4→8 |
| ③ | SLA/制冷仍缺失 | query 词汇鸿沟：checklist 写「SLA 可用性」，标书写「业务连续性 99.99%」 | query 用行业同义词扩展 |
| ④ | 罚则项从达标退步 | 图描述入库后挤占了文本项的检索窗口 | 按维度定向检索（文本项只检文本） |

**核心认知：检索为空 ≠ 内容缺失。** 做审核/评估前必须先验证数据管道的每一环，否则结论全错。这套排雷方法论，比"我搭了个多模态系统"经得起追问。

## 评估（诚实标注）

P3 是**审核任务**，没有现成 gold answer——真实"漏检/误检"的基准是读过整份标书的领域专家。所以评估分三轴，各归其位：

| 轴 | 方式 | 结果 |
|---|---|---|
| **召回诊断** | 全自动：k=8 证据 vs 深捞 k=25 | 12 项中 10 项 k=8 外仍有关键证据，标出高危复核点 |
| **忠实度（抗幻觉）** | 全自动：AI 出处是否在知识库真实存在 | **12/12 有据，0 幻觉** |
| **对错判断** | 专家填 `eval/expert_labels.csv` → 算一致率/漏检率/误检率 | 需人工，样本 1 份不宣称统计意义 |

> ⚠️ 忠实度只证「没编造出处」，**不等于判断正确**；样本量为 1 份标书 × 12 项，方法论验证级。

## 运行

### 本地

```bash
pip install -r requirements.txt
cp .env.example .env          # 填入 DASHSCOPE_API_KEY
python app.py                 # 浏览器打开 http://localhost:7860
```

命令行方式（不用前端）：

```bash
python src/multimodal_rag.py build_full          # 全量文本入库
python src/multimodal_rag.py build_images 20     # 抽样 20 张图 VLM 读图入库
python src/audit_agent.py                        # 逐项审核 → data/audit_result.json
python src/report.py                             # 生成 data/audit_report.md
```

### Docker

```bash
docker build -t bid-review .
docker run -p 7860:7860 -e DASHSCOPE_API_KEY=sk-xxx bid-review
```

> DashScope 是国内服务：若开代理，需将 `dashscope.aliyuncs.com` 设为直连/规则模式，
> 否则全局代理绕境外会导致 `APIConnectionError`。

## 数据安全

真实应标书含公司名/项目/报价等敏感信息，**全部本地处理、绝不入公开仓**：
`data/raw`（原始标书）、`data/parsed`（抽出的图）、`data/chroma_db`（向量+图描述）、
审核产物与 `eval/eval_sheet.md`（引用标书原文）均已 `.gitignore` 挡死。
作为求职作品公开时，演示截图中的公司名/报价需打码或替换。

## 目录

```
src/          docx_parser · vlm · multimodal_rag · audit_agent · report
eval/         recall_probe(召回诊断) · faithfulness(抗幻觉) · make_eval_sheet · score_eval
checklist.yaml  审核清单(12 项，5 维度)
app.py        Gradio 前端
docs/design.md  需求与设计
```

## 已知局限

- **拓扑图**：多为 emf 矢量格式，qwen-vl-max 不支持，需先转 png（当前拓扑维度靠文本判断）。
- **图抽样**：docx 解析丢失了图-文位置关联，只能按格式/大小粗筛，非语义抽样。
- **分块**：docx 表格按行切，长表被拆成碎片行，影响强制响应项等表格类审核的召回。

