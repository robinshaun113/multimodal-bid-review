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
from docx.document import Document as _Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.oxml.ns import qn


def iter_blocks(parent):
    """Yield paragraphs and tables in their original document order."""
    parent_elm = parent.element.body if isinstance(parent, _Document) else parent._tc
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def extract_text_chunks(doc):
    """Preserve paragraph/table order, heading context and stable block indexes."""
    chunks = []
    section = ""
    table_index = 0
    for block_index, block in enumerate(iter_blocks(doc)):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            style = (block.style.name or "") if block.style else ""
            if style.lower().startswith(("heading", "标题")) and text:
                section = text
            if text:
                chunks.append(
                    {
                        "text": text,
                        "kind": "paragraph",
                        "block_index": block_index,
                        "section": section,
                        "style": style,
                    }
                )
            continue

        rows = []
        for row in block.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            chunks.append(
                {
                    "text": "\n".join(rows),
                    "kind": "table",
                    "table_index": table_index,
                    "block_index": block_index,
                    "section": section,
                }
            )
        table_index += 1
    return chunks


def _image_anchors(doc):
    """Map OOXML relationship IDs to nearby section/block context."""
    anchors: dict[str, list[dict]] = {}
    section = ""
    for block_index, block in enumerate(iter_blocks(doc)):
        if not isinstance(block, Paragraph):
            continue
        text = block.text.strip()
        style = (block.style.name or "") if block.style else ""
        if style.lower().startswith(("heading", "标题")) and text:
            section = text
        for blip in block._p.xpath(".//a:blip"):
            rel_id = blip.get(qn("r:embed"))
            if not rel_id or rel_id not in doc.part.rels:
                continue
            target = doc.part.rels[rel_id].target_ref
            name = os.path.basename(target)
            anchors.setdefault(name, []).append(
                {"block_index": block_index, "section": section, "paragraph": text[:200]}
            )
    return anchors


def extract_images(docx_path, out_dir, doc=None):
    """docx=zip，从 word/media/ 提取内嵌图到 out_dir。返回 [{image_path, rid, ext}]。"""
    os.makedirs(out_dir, exist_ok=True)
    imgs = []
    anchors = _image_anchors(doc) if doc is not None else {}
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
            nearby = anchors.get(name, [])
            first = nearby[0] if nearby else {}
            imgs.append({
                "image_path": dst,
                "rid": name,
                "ext": ext,
                "anchors": nearby,
                "block_index": first.get("block_index"),
                "section": first.get("section", ""),
            })
    return imgs


def parse_docx(docx_path, image_out_dir=None):
    """主入口：返回 {text_chunks, image_chunks, meta}。"""
    docx_path = str(docx_path)
    if image_out_dir is None:
        image_out_dir = str(Path(docx_path).parent.parent / "parsed" / "images")
    doc = docx.Document(docx_path)
    text_chunks = extract_text_chunks(doc)
    image_chunks = extract_images(docx_path, image_out_dir, doc=doc)
    digest = __import__("hashlib").sha256()
    with open(docx_path, "rb") as source_file:
        for block in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "text_chunks": text_chunks,
        "image_chunks": image_chunks,
        "meta": {
            "source": os.path.basename(docx_path),
            "document_id": digest.hexdigest()[:16],
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
