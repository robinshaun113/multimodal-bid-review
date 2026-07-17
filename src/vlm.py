"""
src/vlm.py — 视觉语言模型(VLM)封装 (Day37)

把应标书里的图（拓扑图/机柜布局/SLA截图/资质证书）转成结构化文字描述，
供下游多模态 RAG 入库与审核。用百炼 qwen-vl-max（OpenAI 兼容接口）。

用法：python src/vlm.py <图片路径>
"""
import os
import base64
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True)

_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_MODEL = "qwen-vl-max"

# 针对 IDC 应标书场景的描述 prompt：抓审核关心的信息，不泛泛而谈
_DESC_PROMPT = """你是 IDC 数据中心技术文档分析专家。请描述这张图，重点提取审核关心的信息：
- 如果是拓扑图/架构图：网络/电力/制冷的结构、冗余设计、关键设备
- 如果是机柜布局图：机柜数量、分区、功率密度线索
- 如果是表格/条款截图：SLA 数值、承诺指标、关键数字
- 如果是资质证书/证明：证书类型、颁发机构
用简洁中文描述，只讲图里真实可见的内容，看不清就说看不清，不要臆测编造。"""


_MAX_BYTES = 2 * 1024 * 1024   # 超 2MB 就压缩(qwen-vl-max 单图有上限，超大图会 400)
_MAX_SIDE = 2048               # 长边像素上限


def _encode_image(image_path):
    """图 → data URL。超大图(>2MB)先用 Pillow 等比压缩+重编码 JPEG，否则 VLM 会 400。"""
    ext = Path(image_path).suffix.lstrip(".").lower()

    if os.path.getsize(image_path) > _MAX_BYTES:
        from PIL import Image
        import io
        Image.MAX_IMAGE_PIXELS = None  # 本地可信标书文件，解除解压炸弹像素上限
        img = Image.open(image_path)
        if img.mode in ("RGBA", "P", "LA"):   # 带透明通道的 png 转 RGB 才能存 JPEG
            img = img.convert("RGB")
        img.thumbnail((_MAX_SIDE, _MAX_SIDE))  # 等比缩放，不超过长边
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"

    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/{mime};base64,{b64}"


def describe_image(image_path, prompt=None, max_tokens=400):
    """图 → 文字描述。返回描述字符串；失败返回以'[VLM失败]'开头的字符串。"""
    client = OpenAI(api_key=os.getenv("DASHSCOPE_API_KEY"), base_url=_BASE_URL,
                    timeout=60, max_retries=2)
    try:
        data_url = _encode_image(image_path)
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt or _DESC_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[VLM失败] {type(e).__name__}: {str(e)[:120]}"


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else None
    if not p:
        print("用法: python src/vlm.py <图片路径>"); sys.exit(1)
    sz = os.path.getsize(p) // 1024
    print(f"图: {os.path.basename(p)} ({sz}KB)")
    print("描述:", describe_image(p))
