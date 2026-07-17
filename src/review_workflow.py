"""Reliable, parallel compliance review workflow built on LangGraph."""

from __future__ import annotations

import operator
from typing import Annotated

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send, interrupt
from typing_extensions import TypedDict

from audit_agent import audit_one
from multimodal_rag import load_index


class ReviewState(TypedDict, total=False):
    document_id: str
    requirements: list[dict]
    requirement: dict
    results: Annotated[list[dict], operator.add]
    require_human_review: bool
    human_review_status: str


def dispatch_requirements(state: ReviewState):
    return [
        Send(
            "audit_requirement",
            {"document_id": state["document_id"], "requirement": requirement},
        )
        for requirement in state["requirements"]
    ]


def audit_requirement(state: ReviewState) -> dict:
    vs = load_index(state["document_id"])
    result = audit_one(state["requirement"], vs=vs)
    return {"results": [result]}


def route_after_audit(state: ReviewState) -> str:
    redline_bad = any(
        (r.get("mandatory") or r.get("level") == "废标红线")
        and r.get("conclusion") in {"风险", "缺失"}
        for r in state.get("results", [])
    )
    return "human_review" if state.get("require_human_review") and redline_bad else "finish"


def gather_results(state: ReviewState) -> dict:
    """Fan-in barrier: reducers have combined all parallel audit results."""
    return {}


def human_review(state: ReviewState) -> dict:
    decision = interrupt(
        {
            "type": "bid_redline_review",
            "message": "检测到强制项风险，请人工确认后再出具报告。",
            "items": [
                r for r in state.get("results", [])
                if (r.get("mandatory") or r.get("level") == "废标红线")
                and r.get("conclusion") in {"风险", "缺失"}
            ],
            "allowed_actions": ["approve", "reject"],
        }
    )
    action = (decision or {}).get("action", "reject") if isinstance(decision, dict) else "reject"
    return {"human_review_status": "approved" if action == "approve" else "rejected"}


def finish(state: ReviewState) -> dict:
    return {}


def build_review_graph(checkpointer=None):
    graph = StateGraph(ReviewState)
    graph.add_node(
        "audit_requirement",
        audit_requirement,
        retry_policy=RetryPolicy(max_attempts=3, initial_interval=1.0),
    )
    graph.add_node("human_review", human_review)
    graph.add_node("gather_results", gather_results)
    graph.add_node("finish", finish)
    graph.add_conditional_edges(START, dispatch_requirements, ["audit_requirement"])
    graph.add_edge("audit_requirement", "gather_results")
    graph.add_conditional_edges(
        "gather_results",
        route_after_audit,
        {"human_review": "human_review", "finish": "finish"},
    )
    graph.add_edge("human_review", "finish")
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)
