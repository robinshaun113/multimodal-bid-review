"""Optional native image-text retrieval using qwen3-vl-embedding.

This is deliberately a separate image collection: text retrieval keeps its
proven production baseline while image retrieval can be evaluated independently
with Recall@K before fusion is enabled by default.
"""

from __future__ import annotations

import os

import chromadb
import httpx
from dotenv import load_dotenv

from docx_parser import parse_docx
from multimodal_rag import _PERSIST_DIR, _pick_images, document_id
from schemas import stable_id
from vlm import _encode_image

load_dotenv(override=True)

_ENDPOINT = (
    "https://dashscope.aliyuncs.com/api/v1/services/embeddings/"
    "multimodal-embedding/multimodal-embedding"
)


class QwenMultimodalEmbeddings:
    def __init__(self, model: str = "qwen3-vl-embedding", timeout: float = 90):
        self.model = model
        self.timeout = timeout
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")

    def _embed(self, content: dict) -> list[float]:
        if not self.api_key:
            raise RuntimeError("缺少 DASHSCOPE_API_KEY")
        response = httpx.post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": {"contents": [content]}},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("output", {}).get("embeddings", [])
        if not embeddings or "embedding" not in embeddings[0]:
            raise RuntimeError(f"多模态向量响应格式异常: {str(payload)[:200]}")
        return embeddings[0]["embedding"]

    def embed_text(self, text: str) -> list[float]:
        return self._embed({"text": text})

    def embed_image(self, image_path: str) -> list[float]:
        return self._embed({"image": _encode_image(image_path)})


def _collection(doc_id: str):
    client = chromadb.PersistentClient(path=_PERSIST_DIR)
    return client.get_or_create_collection(
        f"bid_images_native_{doc_id}",
        metadata={"hnsw:space": "cosine"},
    )


def build_native_image_index(docx_path: str, sample: int = 60, embedder=None):
    parsed = parse_docx(docx_path)
    doc_id = parsed["meta"]["document_id"]
    images = _pick_images(parsed["image_chunks"], sample=sample)
    embedder = embedder or QwenMultimodalEmbeddings()
    collection = _collection(doc_id)

    for image in images:
        evidence_id = stable_id("evimg", parsed["meta"]["source"], image["rid"])
        metadata = {
            "type": "image",
            "source": parsed["meta"]["source"],
            "rid": image["rid"],
            "image_path": image["image_path"],
            "section": image.get("section", ""),
        }
        collection.upsert(
            ids=[evidence_id],
            embeddings=[embedder.embed_image(image["image_path"])],
            documents=[image.get("section") or image["rid"]],
            metadatas=[metadata],
        )
    return doc_id


def query_native_images(question: str, doc_id: str, k: int = 5, embedder=None) -> list[dict]:
    embedder = embedder or QwenMultimodalEmbeddings()
    result = _collection(doc_id).query(
        query_embeddings=[embedder.embed_text(question)],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    rows = []
    for evidence_id, metadata, distance in zip(
        result["ids"][0], result["metadatas"][0], result["distances"][0]
    ):
        rows.append(
            {
                "type": "image",
                "evidence_id": evidence_id,
                "rid": metadata.get("rid"),
                "image_path": metadata.get("image_path"),
                "source": metadata.get("source"),
                "section": metadata.get("section", ""),
                "distance": distance,
            }
        )
    return rows
