"""
src/docx_parser.py — 应标技术标书(docx)解析器 (Day38)

把一份 docx 应标书拆成统一格式：
  {text_chunks: [{text, kind}], image_chunks: [{image_path, rid, ext}]}

- 文本：python-docx 按段落 + 表格抽取
- 图片：docx 本质是 zip，直接从 word/media/ 提取内嵌图（应标书含几百张拓扑/机柜布局图）
- docx 非 PDF，故不用 PyMuPDF；结构化程度比扫描件 PDF 更好

用法：python src/docx_parser.py <docx路径>
"""
import os
import sys
import zipfile
from pathlib import Path

import docx  # python-docx


def extract_text_chunks(doc):
    """按段落 + 表格抽文本，过滤空段。返回 [{text, kind}]。"""
    chunks = []
    for para in doc.paragraphs:
        t = para.text.strip()
        if t:
            chunks.append({"text": t, "kind": "paragraph"})
    for ti, table in enumerate(doc.tables):
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            line = " | ".join(c for c in cells if c)
            if line:
                chunks.append({"text": line, "kind": f"table{ti}"})
    return chunks


def extract_images(docx_path, out_dir):
    """docx=zip，从 word/media/ 提取内嵌图到 out_dir。返回 [{image_path, rid, ext}]。"""
    os.makedirs(out_dir, exist_ok=True)
    imgs = []
    with zipfile.ZipFile(docx_path) as z:
        media = [n for n in z.namelist() if n.startswith("word/media/")]
        for n in media:
            ext = n.rsplit(".", 1)[-1].lower()
            if ext not in ("jpeg", "jpg", "png", "emf", "wmf", "gif", "bmp"):
                continue
            name = os.path.basename(n)
            dst = os.path.join(out_dir, name)
            with z.open(n) as src, open(dst, "wb") as f:
                f.write(src.read())
            imgs.append({"image_path": dst, "rid": name, "ext": ext})
    return imgs


def parse_docx(docx_path, image_out_dir=None):
    """主入口：返回 {text_chunks, image_chunks, meta}。"""
    docx_path = str(docx_path)
    if image_out_dir is None:
        image_out_dir = str(Path(docx_path).parent.parent / "parsed" / "images")
    doc = docx.Document(docx_path)
    text_chunks = extract_text_chunks(doc)
    image_chunks = extract_images(docx_path, image_out_dir)
    return {
        "text_chunks": text_chunks,
        "image_chunks": image_chunks,
        "meta": {
            "source": os.path.basename(docx_path),
            "n_text": len(text_chunks),
            "n_image": len(image_chunks),
        },
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("用法: python src/docx_parser.py <docx路径>"); sys.exit(1)
    r = parse_docx(path)
    m = r["meta"]
    print(f"解析: {m['source']}")
    print(f"文本块: {m['n_text']} | 图片: {m['n_image']}")
    print("--- 前3个文本块 ---")
    for c in r["text_chunks"][:3]:
        print(f"  [{c['kind']}] {c['text'][:60]}")
    print("--- 前3张图 ---")
    for im in r["image_chunks"][:3]:
        sz = os.path.getsize(im["image_path"]) // 1024
        print(f"  {im['rid']} ({im['ext']}, {sz}KB)")
