"""
app.py — 多模态应标书审核 · Gradio 前端 (Day44)

流程：上传 docx → 解析 → 全量文本入库 + 抽样图入库(VLM读图) → 审核 → 报告预览/下载

⚠️ 安全说明：本应用为【本地开发/演示】用途，未内置身份认证。
   - 上传的应标书含敏感商业信息，请仅在本地或可信内网运行，勿暴露公网。
   - DASHSCOPE_API_KEY 经环境变量注入，不写入代码/镜像。
"""
import os
import sys
import shutil
import tempfile

import gradio as gr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from docx_parser import parse_docx
from multimodal_rag import build_full_text_index, build_image_index
from audit_agent import audit_all
from report import render_report

_ROOT = os.path.dirname(__file__)
_RAW_DIR = os.path.join(_ROOT, "data", "raw")


def run_pipeline(docx_file, img_sample, progress=gr.Progress()):
    """跑完整五环 pipeline，返回 (报告markdown, 报告文件路径)。"""
    if docx_file is None:
        return "请先上传一份 .docx 应标书。", None
    if not str(docx_file).lower().endswith(".docx"):
        return "只支持 .docx 格式（应标书通常为 Word 文档）。", None

    # 拷进 data/raw（受 gitignore 保护，不会误提交）
    os.makedirs(_RAW_DIR, exist_ok=True)
    dst = os.path.join(_RAW_DIR, os.path.basename(str(docx_file)))
    shutil.copy(str(docx_file), dst)

    progress(0.05, desc="① 解析 docx（文本 + 内嵌图）")
    parsed = parse_docx(dst)
    n_text, n_img = parsed["meta"]["n_text"], parsed["meta"]["n_image"]

    progress(0.20, desc=f"② 全量文本入库（{n_text} 块，去重过滤后分批 embedding）")
    build_full_text_index(dst)

    progress(0.45, desc=f"③ 抽样 {img_sample} 张图 → VLM 读图 → 描述入库（较慢）")
    build_image_index(dst, sample=int(img_sample))

    progress(0.80, desc="④ 逐项审核（检索 + LLM 对照 checklist）")
    results = audit_all()

    progress(0.95, desc="⑤ 生成报告")
    md = render_report(results)
    out = os.path.join(_ROOT, "data", "audit_report.md")

    progress(1.0, desc="完成")
    summary = f"解析：{n_text} 文本块 + {n_img} 张图（抽样入库 {img_sample} 张）"
    return f"> {summary}\n\n{md}", out


_INTRO = """# 多模态 IDC 应标技术标书智能审核

上传一份 **.docx 应标技术标书**，系统自动：docx 解析 → 全量文本 + VLM 读图入库
→ 按 checklist 逐项审核（废标红线/关键指标/图纸完整性）→ 生成审核报告。

⚠️ **本地演示用，无鉴权**：标书含敏感商业信息，请仅在本地/可信内网运行。
图入库需逐张调用 VLM，抽样张数越多越慢；演示建议 20 张。
"""


def build_ui():
    with gr.Blocks(title="多模态应标书审核") as demo:
        gr.Markdown(_INTRO)
        with gr.Row():
            with gr.Column(scale=1):
                docx_in = gr.File(label="上传应标书 (.docx)", file_types=[".docx"])
                img_slider = gr.Slider(5, 60, value=20, step=5,
                                       label="图抽样张数（越多越慢）")
                run_btn = gr.Button("开始审核", variant="primary")
                report_file = gr.File(label="下载报告 (.md)")
            with gr.Column(scale=2):
                report_md = gr.Markdown(label="审核报告预览")
        run_btn.click(run_pipeline, inputs=[docx_in, img_slider],
                      outputs=[report_md, report_file])
    return demo


if __name__ == "__main__":
    build_ui().queue().launch(server_port=7860)
