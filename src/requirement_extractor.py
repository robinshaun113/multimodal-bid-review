"""Extract auditable requirements from a tender document.

The LLM extracts; deterministic code assigns IDs, preserves source evidence and
deduplicates. Numeric compliance is evaluated downstream, not invented here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from docx_parser import parse_docx
from schemas import Requirement, RequirementBatch, stable_id

load_dotenv(override=True)


def _get_llm():
    model = os.getenv("QWEN_TEXT_MODEL", "qwen3.7-plus")
    return ChatOpenAI(
        model=model,
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0,
    ).with_structured_output(RequirementBatch, method="function_calling")


def _batches(chunks: list[dict], max_chars: int = 12000):
    batch, size = [], 0
    for chunk in chunks:
        text = chunk["text"].strip()
        if not text:
            continue
        item = {
            "block_index": chunk["block_index"],
            "section": chunk.get("section", ""),
            "text": text,
        }
        if batch and size + len(text) > max_chars:
            yield batch
            batch, size = [], 0
        batch.append(item)
        size += len(text)
    if batch:
        yield batch


def extract_requirements(tender_path: str, llm=None, max_requirements: int = 80) -> list[Requirement]:
    parsed = parse_docx(tender_path)
    llm = llm or _get_llm()
    by_block = {x["block_index"]: x for x in parsed["text_chunks"]}
    extracted: list[Requirement] = []
    seen = set()

    for group in _batches(parsed["text_chunks"]):
        context = "\n\n".join(
            f"[BLOCK {x['block_index']} | {x['section'] or '未命名章节'}]\n{x['text']}"
            for x in group
        )
        prompt = f"""你是招投标解决方案顾问。请从以下招标文件片段抽取可核验的技术、服务、
商务和图纸要求。只抽取应标方需要明确响应的要求，不总结背景介绍。

规则：
1. ★、▲、必须、不得、不低于、不超过等通常是强制项；
2. 保留阈值、单位、时间、等级和冗余方式；
3. source_quote 必须逐字来自输入，source_block_index 必须对应 BLOCK；
4. 同一要求不要重复；不确定时宁缺毋滥。

{context}"""
        result = llm.invoke(prompt)
        for draft in result.requirements:
            source = by_block.get(draft.source_block_index)
            if source is None or draft.source_quote not in source["text"]:
                continue
            dedupe_key = (draft.dimension.strip(), draft.expected.strip())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            req_id = stable_id(
                "req", Path(tender_path).name, draft.source_block_index, draft.expected
            )
            extracted.append(
                Requirement(
                    requirement_id=req_id,
                    dimension=draft.dimension.strip(),
                    query=f"{draft.dimension} {draft.expected} {draft.source_quote}",
                    expected=draft.expected.strip(),
                    mandatory=draft.mandatory,
                    level="废标红线" if draft.mandatory else draft.level,
                    tender_evidence_id=stable_id(
                        "tender", Path(tender_path).name, draft.source_block_index, source["text"]
                    ),
                    tender_quote=draft.source_quote,
                    tender_section=source.get("section", ""),
                    origin="tender",
                )
            )
            if len(extracted) >= max_requirements:
                return extracted
    return extracted


def save_requirements(requirements: list[Requirement], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps([r.model_dump() for r in requirements], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
