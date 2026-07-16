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

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

sys.path.insert(0, os.path.dirname(__file__))
from docx_parser import parse_docx
from vlm import describe_image

load_dotenv(override=True)

_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "chroma_db")
_COLLECTION = "bid_multimodal"


def get_embeddings():
    """百炼 text-embedding-v2（复用 P1 经验；check_embedding_ctx_length=False 避免报错）。"""
    return OpenAIEmbeddings(
        model="text-embedding-v2",
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        check_embedding_ctx_length=False,
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


def load_index():
    """加载已建好的向量库。"""
    return Chroma(
        collection_name=_COLLECTION,
        embedding_function=get_embeddings(),
        persist_directory=_PERSIST_DIR,
    )


def query(question, k=4, vs=None):
    """检索：返回命中条目。图(type=image)顺 image_path 带回原图路径。"""
    vs = vs or load_index()
    hits = vs.similarity_search(question, k=k)
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
            })
        else:
            results.append({"type": "text", "content": h.page_content})
    return results


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        docx = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
        import glob
        files = glob.glob(os.path.join(docx, "*.docx"))
        if not files:
            print("data/raw 无 docx"); sys.exit(1)
        build_index(files[0])
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
