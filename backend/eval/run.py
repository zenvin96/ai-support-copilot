"""评估：意图准确率 / 工具选择正确率 / RAG 命中率（top-3）。

用法（容器内）：docker compose exec backend python -m eval.run
需要先在 /knowledge 上传 sample_docs 下的三个文档。
"""
import asyncio
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.db.models import AgentRun
from app.db.session import SessionLocal, engine
from app.services.agent.graph import RunContext, graph
from app.services.agent.runner import _contexts  # noqa: F401
from app.services.db_bootstrap import ensure_ready
from app.services.rag.retriever import retrieve
from app.services.usage.tracker import UsageCallback


async def one(case: dict) -> dict:
    async with SessionLocal() as db:
        run = AgentRun(user_query=case["query"], model=get_settings().default_model)
        db.add(run)
        await db.commit()
        run_id = run.id
    ctx = RunContext(run_id=run_id, model=get_settings().default_model, usage=UsageCallback(run_id))
    config = {"configurable": {"thread_id": f"eval-{run_id}", "ctx": ctx}}
    final = {}
    async for mode, chunk in graph.astream({"query": case["query"], "history": [], "conversation_id": None},
                                           config=config, stream_mode=["updates"]):
        if isinstance(chunk, dict):
            for v in chunk.values():
                if isinstance(v, dict):
                    final.update(v)
    used_tools = {r["tool"] for r in final.get("tool_results", [])}
    expected_tools = set(case["tools"])
    hit = None
    if case["doc"]:
        cits = await retrieve(case["query"], top_k=3)
        hit = any(c.filename == case["doc"] for c in cits)
    return {"query": case["query"], "intent_ok": final.get("intent") == case["intent"],
            "got_intent": final.get("intent"),
            "tools_ok": expected_tools.issubset(used_tools) if expected_tools else not used_tools,
            "got_tools": sorted(used_tools), "rag_hit": hit, "tokens": ctx.usage.total_tokens}


async def main() -> None:
    await ensure_ready()
    cases = [json.loads(line) for line in Path(__file__).with_name("cases.jsonl").read_text().splitlines() if line.strip()]
    results = [await one(c) for c in cases]
    n = len(results)
    intent_acc = sum(r["intent_ok"] for r in results) / n
    tool_acc = sum(r["tools_ok"] for r in results) / n
    rag_cases = [r for r in results if r["rag_hit"] is not None]
    rag_acc = sum(r["rag_hit"] for r in rag_cases) / max(len(rag_cases), 1)
    print(f"\n{'query':<40} {'intent':<8} {'tools':<8} {'rag':<6} {'tokens':>6}")
    for r in results:
        print(f"{r['query'][:38]:<40} {'✓' if r['intent_ok'] else '✗ ' + str(r['got_intent']):<8} "
              f"{'✓' if r['tools_ok'] else '✗ ' + ','.join(r['got_tools']):<8} "
              f"{'-' if r['rag_hit'] is None else ('✓' if r['rag_hit'] else '✗'):<6} {r['tokens']:>6}")
    print(f"\n意图准确率   {intent_acc:.0%}\n工具选择正确率 {tool_acc:.0%}\nRAG top-3 命中率 {rag_acc:.0%}  (n={len(rag_cases)})")
    print(f"总 tokens {sum(r['tokens'] for r in results)}")
    await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
