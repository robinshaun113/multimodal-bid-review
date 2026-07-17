"""
app.py — 多模态应标书审核 · Gradio 前端 (Day44)

流程：上传招标+应标 docx → 抽取招标要求 → 建应标多模态证据索引
→ 逐项合规审核 → 报告预览/下载

⚠️ 安全说明：本应用为【本地开发/演示】用途，未内置身份认证。
   - 上传的应标书含敏感商业信息，请仅在本地或可信内网运行，勿暴露公网。
   - DASHSCOPE_API_KEY 经环境变量注入，不写入代码/镜像。
"""
import os
import sys
import shutil
import hashlib
from pathlib import Path

import gradio as gr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from docx_parser import parse_docx
from multimodal_rag import build_full_text_index, build_image_index, document_id
from audit_agent import load_checklist
from requirement_extractor import extract_requirements, save_requirements
from schemas import baseline_requirement
from review_workflow import build_review_graph
from report import render_report

_ROOT = os.path.dirname(__file__)
_RAW_DIR = os.path.join(_ROOT, "data", "raw")


def _validate_docx(path, label):
    if path is None:
        return f"请先上传{label}。"
    path = Path(str(path))
    if path.suffix.lower() != ".docx":
        return f"{label}仅支持 .docx。"
    if path.stat().st_size > 500 * 1024 * 1024:
        return f"{label}不能超过 500MB。"
    return None


def _copy_input(path, prefix):
    os.makedirs(_RAW_DIR, exist_ok=True)
    src = Path(str(path))
    digest = hashlib.sha256()
    with src.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    safe_stem = "".join(
        char for char in src.stem if char.isalnum() or char in {"-", "_"}
    )[:60] or "document"
    dst = Path(_RAW_DIR) / f"{prefix}_{digest.hexdigest()[:12]}_{safe_stem}.docx"
    shutil.copy(str(src), dst)
    return str(dst)


def run_pipeline(tender_file, response_file, img_sample, progress=gr.Progress()):
    """跑双文档合规审核；招标文件可选，缺省时使用行业基准 Checklist。"""
    error = _validate_docx(response_file, "应标文件")
    if error:
        return error, None
    if tender_file is not None:
        error = _validate_docx(tender_file, "招标文件")
        if error:
            return error, None

    response_path = _copy_input(response_file, "response")
    tender_path = _copy_input(tender_file, "tender") if tender_file else None
    doc_id = document_id(response_path)

    progress(0.05, desc="① 解析应标文件（保留段落/表格顺序与图片锚点）")
    parsed = parse_docx(response_path)
    n_text, n_img = parsed["meta"]["n_text"], parsed["meta"]["n_image"]

    if tender_path:
        progress(0.12, desc="② 从招标文件抽取可核验要求")
        requirements = extract_requirements(tender_path)
        if not requirements:
            return "未能从招标文件抽取有效要求，请检查文档内容。", None
    else:
        requirements = [baseline_requirement(x) for x in load_checklist()]

    requirements_path = os.path.join(_ROOT, "data", f"requirements_{doc_id}.json")
    save_requirements(requirements, requirements_path)

    progress(0.25, desc=f"③ 全量应标文本入库（{n_text} 块）")
    vs = build_full_text_index(response_path, doc_id=doc_id)

    progress(0.48, desc=f"④ 抽样 {img_sample} 张图 → VLM 读图 → 证据入库")
    build_image_index(
        response_path, sample=int(img_sample), doc_id=doc_id, vs=vs
    )

    progress(0.78, desc=f"⑤ 并逐项核对 {len(requirements)} 条招标/基准要求")
    graph = build_review_graph()
    graph_result = graph.invoke(
        {
            "document_id": doc_id,
            "requirements": [r.model_dump() for r in requirements],
            # Web demo renders risks but does not block the request for a second
            # interaction. CLI/production callers can enable the interrupt path.
            "require_human_review": False,
        },
        config={"max_concurrency": 3},
    )
    results = graph_result["results"]
    result_path = os.path.join(_ROOT, "data", f"audit_result_{doc_id}.json")
    Path(result_path).write_text(
        __import__("json").dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    progress(0.95, desc="⑥ 生成合规矩阵报告")
    md = render_report(results)
    out = os.path.join(_ROOT, "data", f"audit_report_{doc_id}.md")
    Path(out).write_text(md, encoding="utf-8")

    progress(1.0, desc="完成")
    mode = "招标—应标对照" if tender_path else "行业基准扫描"
    summary = (
        f"模式：{mode}｜要求 {len(requirements)} 条｜"
        f"应标证据：{n_text} 文本块 + {n_img} 张图（抽样 {img_sample} 张）"
    )
    return f"> {summary}\n\n{md}", out


_INTRO = """# 多模态 IDC 应标技术标书智能审核

上传 **招标文件 + 应标文件** 后，系统从招标文件抽取强制项和阈值，再从应标文件
检索文本/图片证据，输出需求—响应合规矩阵。也可不传招标文件，使用行业基准扫描模式。

⚠️ **本地演示用，无鉴权**：文件和产物保存在本地，但选定文本和图片会发送到
百炼云端 API 做 embedding/VLM/LLM 推理。敏感标书需先脱敏或切换私有化模型。
图入库需逐张调用 VLM，抽样张数越多越慢；演示建议 20 张。
"""


def build_ui():
    with gr.Blocks(title="多模态应标书审核") as demo:
        gr.Markdown(_INTRO)
        with gr.Row():
            with gr.Column(scale=1):
                tender_in = gr.File(
                    label="招标文件 (.docx，可选；不传则用行业基准)",
                    file_types=[".docx"],
                )
                response_in = gr.File(label="应标文件 (.docx)", file_types=[".docx"])
                img_slider = gr.Slider(5, 60, value=20, step=5,
                                       label="图抽样张数（越多越慢）")
                run_btn = gr.Button("开始审核", variant="primary")
                report_file = gr.File(label="下载报告 (.md)")
            with gr.Column(scale=2):
                report_md = gr.Markdown(label="审核报告预览")
        run_btn.click(run_pipeline, inputs=[tender_in, response_in, img_slider],
                      outputs=[report_md, report_file])
    return demo


if __name__ == "__main__":
    build_ui().queue().launch(server_port=7860)
