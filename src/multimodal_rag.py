"""
src/multimodal_rag.py — 多模态 RAG (Day39)

灵魂：embedding 只吃文字，所以图不能直接入库——
  文本块 → 直接 embedding 入库
  图片   → VLM 转文字描述 → embedding 入库，metadata 存 image_path 拴住原图
检索命中后：type=text 直接用；type=image 顺 image_path 找回原图。

用法：python src/multimodal_rag.py build   # 小批入库
     python src/multimodal_rag.py query "机柜怎么布局"
"""
import os
import sys
import hashlib

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

sys.path.insert(0, os.path.dirname(__file__))
from docx_parser import parse_docx
from vlm import describe_image
from schemas import stable_id

load_dotenv(override=True)

_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "chroma_db")
_COLLECTION = "bid_multimodal"


def document_id(docx_path: str) -> str:
    """Hash document content without loading a several-hundred-MB file into memory."""
    digest = hashlib.sha256()
    with open(docx_path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()[:16]


def collection_name(doc_id: str | None = None) -> str:
    return f"bid_response_{doc_id}" if doc_id else _COLLECTION


def _text_metadata(parsed: dict, chunk: dict, ordinal: int) -> dict:
    source = parsed["meta"]["source"]
    block_index = int(chunk.get("block_index", ordinal))
    return {
        "type": "text",
        "source": source,
        "document_id": parsed["meta"]["document_id"],
        "kind": chunk["kind"],
        "block_index": block_index,
        "section": chunk.get("section", ""),
        "evidence_id": stable_id("ev", source, block_index, chunk["text"]),
    }


def get_embeddings():
    """百炼 text-embedding-v2（复用 P1 经验；check_embedding_ctx_length=False 避免报错）。

    chunk_size=10：DashScope 兼容模式单次 batch 上限 25 条，全量入库时靠它分批，
    否则 4011 条文本一次性 embed 会被服务端拒。
    """
    return OpenAIEmbeddings(
        model="text-embedding-v2",
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        check_embedding_ctx_length=False,
        chunk_size=10,
    )


def build_index(docx_path, text_limit=15, image_limit=10):
    """小批入库：文本块 + 图(VLM转描述)。返回 Chroma 向量库。"""
    parsed = parse_docx(docx_path)
    docs = []

    # ① 文本块 → Document(type=text)，直接入库
    for c in parsed["text_chunks"][:text_limit]:
        docs.append(Document(
            page_content=c["text"],
            metadata={"type": "text", "kind": c["kind"]},
        ))
    print(f"文本 Document: {len(docs)} 个")

    # ② 图 → VLM 转描述 → Document(type=image, 存 image_path 拴原图)
    n_img = 0
    for im in parsed["image_chunks"][:image_limit]:
        desc = describe_image(im["image_path"])
        if desc.startswith("[VLM失败]"):
            print(f"  跳过 {im['rid']}: {desc[:40]}")
            continue
        docs.append(Document(
            page_content=desc,                       # 入库的是"描述文字"，不是图本身
            metadata={"type": "image",
                      "image_path": im["image_path"],  # 挂钩原图
                      "rid": im["rid"]},
        ))
        n_img += 1
        print(f"  图 {im['rid']} → 描述({len(desc)}字)入库")
    print(f"图 Document: {n_img} 个 | 总计: {len(docs)}")

    # ③ 一起入 Chroma
    vs = Chroma.from_documents(
        documents=docs,
        embedding=get_embeddings(),
        collection_name=_COLLECTION,
        persist_directory=_PERSIST_DIR,
    )
    print(f"✓ 入库完成，持久化到 {_PERSIST_DIR}")
    return vs


def build_full_text_index(docx_path, min_len=5, doc_id=None):
    """全量文本入库（Day46）：把整份标书的文本块都灌进库，修复'假缺失'。

    与 build_index 的区别：
      - build_index 是 Day39 的小批(15+10)链路验证，不代表真实召回；
      - 本函数入全量文本(不含图，图纸维度第二段单独处理)，让文本类 checklist
        (SLA/PUE/强制响应项…) 能真正被检索到。
    过滤：去重 + 丢弃 <min_len 的碎片(页码/单字符/纯符号)，避免污染检索。
    """
    parsed = parse_docx(docx_path)
    seen = set()
    docs = []
    for ordinal, c in enumerate(parsed["text_chunks"]):
        t = c["text"].strip()
        if len(t) < min_len or t in seen:
            continue
        seen.add(t)
        docs.append(Document(
            page_content=t,
            metadata=_text_metadata(parsed, c, ordinal),
        ))
    raw_n = len(parsed["text_chunks"])
    print(f"文本块: 原始 {raw_n} → 去重/过滤后 {len(docs)} 个入库")

    # 先清空旧库(含 Day39 的 25 条测试样本)，避免真假数据混淆
    doc_id = doc_id or parsed["meta"]["document_id"]
    target_collection = collection_name(doc_id)
    vs = Chroma(
        collection_name=target_collection,
        embedding_function=get_embeddings(),
        persist_directory=_PERSIST_DIR,
    )
    try:
        vs.delete_collection()
        print("已清空旧 collection(含 Day39 测试样本)")
    except Exception as e:
        print(f"清空旧库跳过: {e}")

    # 分批入库(chunk_size=10 控制 embedding batch；Chroma add 再按 500 一批持久化)
    vs = Chroma(
        collection_name=target_collection,
        embedding_function=get_embeddings(),
        persist_directory=_PERSIST_DIR,
    )
    B = 500
    for i in range(0, len(docs), B):
        vs.add_documents(docs[i:i + B])
        print(f"  已入库 {min(i + B, len(docs))}/{len(docs)}")
    print(f"[OK] 全量文本入库完成 -> {_PERSIST_DIR} / {target_collection}")
    return vs


def _pick_images(image_chunks, sample=60):
    """图抽样(Day46)：信号弱(无图-文位置关联)，只能靠图自身特征粗筛。
      - 排除 emf/wmf：qwen-vl-max 不支持矢量格式(实测 400)，要读得先转 png(遗留)
      - jpeg/png 按文件大小 top 取(大图更可能是拓扑/机柜布局，小图多为图标)
    返回抽样后的 image_chunks 子集。
    """
    raster = [im for im in image_chunks if im["ext"] in ("jpeg", "jpg", "png")]
    skipped = len(image_chunks) - len(raster)
    raster.sort(key=lambda im: os.path.getsize(im["image_path"]), reverse=True)
    picked = raster[:sample]
    print(f"图抽样: 全{len(image_chunks)}张 → 位图{len(raster)}张(排除矢量{skipped}) → 抽top{len(picked)}张")
    return picked


def build_image_index(docx_path, sample=60, doc_id=None, vs=None):
    """追加图入库(Day46)：不动已入库的文本，只把抽样图经 VLM 转描述后 add 进去。
    修复'图纸维度 VLM 缺席'——让审核真正基于 VLM 读图，而非文本里搜'提到图'。
    """
    parsed = parse_docx(docx_path)
    picked = _pick_images(parsed["image_chunks"], sample=sample)

    doc_id = doc_id or parsed["meta"]["document_id"]
    vs = vs or load_index(doc_id)  # 追加，不清空(文本还在里面)
    # 可重入：先删已有 image 记录(避免多次跑重复入库)，文本保留不动
    try:
        vs.delete(where={"type": "image"})
    except Exception as e:
        print(f"清理旧图记录跳过: {e}")
    docs, ok, fail = [], 0, 0
    for i, im in enumerate(picked, 1):
        desc = describe_image(im["image_path"])
        if desc.startswith("[VLM失败]"):
            fail += 1
            print(f"  [{i}/{len(picked)}] 跳过 {im['rid']}: {desc[:40]}")
            continue
        block_index = im.get("block_index")
        metadata = {
            "type": "image",
            "source": parsed["meta"]["source"],
            "document_id": doc_id,
            "image_path": im["image_path"],
            "rid": im["rid"],
            "section": im.get("section", ""),
            "evidence_id": stable_id("evimg", parsed["meta"]["source"], im["rid"], desc),
        }
        if block_index is not None:
            metadata["block_index"] = int(block_index)
        docs.append(Document(
            page_content=desc,
            metadata=metadata,
        ))
        ok += 1
        if i % 10 == 0 or i == len(picked):
            print(f"  [{i}/{len(picked)}] 已描述 {ok} 张(失败 {fail})")
        # 每 20 张 flush 一次入库，防中途挂全丢
        if len(docs) >= 20:
            vs.add_documents(docs); docs = []
    if docs:
        vs.add_documents(docs)
    print(f"[OK] 图入库完成: 成功 {ok} 张, 失败 {fail} 张")
    return vs


def load_index(doc_id=None):
    """加载已建好的向量库。"""
    return Chroma(
        collection_name=collection_name(doc_id),
        embedding_function=get_embeddings(),
        persist_directory=_PERSIST_DIR,
    )


def query(question, k=4, vs=None, only_type=None):
    """检索：返回命中条目。图(type=image)顺 image_path 带回原图路径。

    only_type='text'/'image' 时按 metadata 过滤(Day46)：图入库后会挤占文本类
    审核项的检索窗口，故文本类维度只检 text、图纸维度才检 image，避免互相污染。
    """
    vs = vs or load_index()
    flt = {"type": only_type} if only_type else None
    hits = vs.similarity_search(question, k=k, filter=flt)
    results = []
    for h in hits:
        t = h.metadata.get("type")
        if t == "image":
            # 图：命中的是"描述"，顺 metadata 找回原图
            results.append({
                "type": "image",
                "desc": h.page_content,
                "image_path": h.metadata.get("image_path"),  # ← 找回的原图
                "rid": h.metadata.get("rid"),
                "evidence_id": h.metadata.get("evidence_id"),
                "source": h.metadata.get("source"),
                "section": h.metadata.get("section", ""),
                "block_index": h.metadata.get("block_index"),
            })
        else:
            results.append({
                "type": "text",
                "content": h.page_content,
                "evidence_id": h.metadata.get("evidence_id"),
                "source": h.metadata.get("source"),
                "section": h.metadata.get("section", ""),
                "block_index": h.metadata.get("block_index"),
            })
    return results


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows GBK 终端防 UnicodeEncodeError
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        docx = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
        import glob
        files = glob.glob(os.path.join(docx, "*.docx"))
        if not files:
            print("data/raw 无 docx"); sys.exit(1)
        build_index(files[0])
    elif cmd == "build_full":
        docx = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
        import glob
        files = glob.glob(os.path.join(docx, "*.docx"))
        if not files:
            print("data/raw 无 docx"); sys.exit(1)
        print(f"全量文本入库: {os.path.basename(files[0])}")
        build_full_text_index(files[0])
    elif cmd == "build_images":
        docx = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
        import glob
        files = glob.glob(os.path.join(docx, "*.docx"))
        if not files:
            print("data/raw 无 docx"); sys.exit(1)
        sample = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        print(f"图入库(抽样{sample}): {os.path.basename(files[0])}")
        build_image_index(files[0], sample=sample)
    elif cmd == "query":
        q = sys.argv[2] if len(sys.argv) > 2 else "机柜布局"
        print(f"问题: {q}\n" + "=" * 50)
        for i, r in enumerate(query(q), 1):
            if r["type"] == "image":
                print(f"[{i}] 🖼️ 图({r['rid']}) → 原图: {r['image_path']}")
                print(f"     描述: {r['desc'][:80]}")
            else:
                print(f"[{i}] 📄 文本: {r['content'][:80]}")
    else:
        print("用法: python src/multimodal_rag.py build | query <问题>")
