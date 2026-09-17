"""Regression coverage for authorization, RAG publication, privacy and conversation state."""
import importlib
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import chromadb
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage, AIMessageChunk
from langgraph.types import Command

from app.api import agent as api
from app.core.security import current_user
from app.db.models import AgentRun, Conversation, Document
from app.db.session import get_db
from app.schemas import AgentRunIn
from app.services.agent.access import owned_run
from app.services.agent.graph import RunContext
from app.services.usage.tracker import UsageCallback

graph_module = importlib.import_module("app.services.agent.graph")
runner = importlib.import_module("app.services.agent.runner")
ingest = importlib.import_module("app.services.rag.ingest")
retriever = importlib.import_module("app.services.rag.retriever")
memory = importlib.import_module("app.services.memory.redis_memory")


class Session:
    def __init__(self, records=None, rows=()):
        self.records = records or {}
        self.rows = rows
        self.add = Mock()
        self.commit = AsyncMock()
        self.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: self.rows))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, model, key, **kwargs):
        return self.records.get((model, key))


@pytest.mark.parametrize("path,body", [
    ("/agent/run", {"query": "test", "conversation_id": 2}),
    ("/agent/resume", {"run_id": 8, "approved": True}),
])
async def test_api_rejects_other_users_before_streaming(monkeypatch, path, body):
    session = Session({(Conversation, 2): SimpleNamespace(user_id=99),
                       (AgentRun, 8): SimpleNamespace(conversation_id=2, status="waiting_confirm")})
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[current_user] = lambda: {"id": 1}
    app.dependency_overrides[get_db] = lambda: session
    start = Mock()
    resume = Mock()
    monkeypatch.setattr(api, "run_agent", start)
    monkeypatch.setattr(api, "resume_agent", resume)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json=body)
    assert response.status_code == 404
    start.assert_not_called()
    resume.assert_not_called()


async def test_owned_run_and_no_conversation_creation(monkeypatch):
    run = SimpleNamespace(conversation_id=2)
    session = Session({(Conversation, 2): SimpleNamespace(user_id=1), (AgentRun, 8): run})
    assert await owned_run(session, 8, 1) is run

    def add(conversation):
        assert conversation.user_id == 1
        conversation.id = 3

    session.add.side_effect = add
    monkeypatch.setattr(api, "check_rate_limit", AsyncMock(return_value=True))
    mocked = Mock(return_value=iter([]))
    monkeypatch.setattr(api, "run_agent", mocked)
    await api.run(AgentRunIn(query="hello"), {"id": 1}, session)
    mocked.assert_called_once_with("hello", 3, None, user_id=1)


async def test_resume_rejects_already_completed_run(monkeypatch):
    session = Session({(Conversation, 2): SimpleNamespace(user_id=1),
                       (AgentRun, 8): SimpleNamespace(conversation_id=2, status="done")})
    monkeypatch.setattr(runner, "SessionLocal", lambda: session)
    events = [json.loads(e["data"]) async for e in runner.resume_agent(8, True, user_id=1)]
    assert events[0]["type"] == "error"
    session.commit.assert_not_awaited()


@pytest.fixture
def index(monkeypatch, tmp_path):
    collection = chromadb.PersistentClient(path=str(tmp_path)).create_collection(
        "regression", metadata={"hnsw:space": "cosine"})
    collection.upsert(ids=["1-0"], documents=["old policy"], embeddings=[[1.0, 0.0]],
                      metadatas=[{"doc_id": 1, "filename": "policy.md", "chunk_index": 0,
                                  "index_version": "legacy"}])
    doc = SimpleNamespace(id=1, filename="policy.md", content="new policy", index_version="legacy",
                          chunk_count=1, status="pending", error=None)
    session = Session({(Document, 1): doc}, rows=[doc])
    for module in (ingest, retriever):
        monkeypatch.setattr(module, "SessionLocal", lambda: session)
        monkeypatch.setattr(module, "get_collection", lambda: collection)
    monkeypatch.setattr(ingest.llm_service, "embed", AsyncMock(side_effect=lambda texts: [[1.0, 0.0] for _ in texts]))
    return collection, doc, session


async def test_embedding_failure_preserves_searchable_old_version(monkeypatch, index):
    collection, doc, _ = index
    monkeypatch.setattr(ingest.llm_service, "embed", AsyncMock(side_effect=RuntimeError("embedding down")))
    await ingest.ingest_text(1, "new policy")
    assert doc.status == "failed"
    assert doc.index_version == "legacy"
    assert collection.get()["documents"] == ["old policy"]
    monkeypatch.setattr(retriever.llm_service, "embed", AsyncMock(return_value=[[1.0, 0.0]]))
    assert [c.text for c in await retriever.retrieve("policy")] == ["old policy"]


async def test_partial_vector_write_failure_preserves_old_version(monkeypatch, index):
    collection, doc, _ = index
    real_upsert = collection.upsert

    def fail_after_write(**kwargs):
        real_upsert(**kwargs)
        raise RuntimeError("connection lost after write")

    monkeypatch.setattr(collection, "upsert", fail_after_write)
    await ingest.ingest_text(1, "new policy")
    assert doc.index_version == "legacy"
    assert collection.get()["documents"] == ["old policy"]


async def test_publish_new_version_and_exclude_staged_chunks(index):
    collection, doc, _ = index
    collection.upsert(ids=["staged"], documents=["unpublished"], embeddings=[[1.0, 0.0]],
                      metadatas=[{"doc_id": 1, "filename": "policy.md", "chunk_index": 0,
                                  "index_version": "unpublished"}])
    assert [c.text for c in await retriever.retrieve("policy")] == ["old policy"]
    await ingest.ingest_text(1, "new policy")
    assert doc.status == "ready" and doc.index_version != "legacy"
    assert [c.text for c in await retriever.retrieve("policy")] == ["new policy"]
    assert collection.get(ids=["1-0"])["ids"] == []


async def test_newer_edit_wins_during_embedding(monkeypatch, index):
    collection, doc, _ = index

    async def embed(texts):
        doc.content = "even newer policy"
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(ingest.llm_service, "embed", embed)
    await ingest.ingest_text(1, "new policy")
    assert doc.content == "even newer policy"
    assert doc.index_version == "legacy"
    assert collection.get()["documents"] == ["old policy"]


async def test_legacy_metadata_migration(index):
    collection, doc, _ = index
    collection.delete(ids=["1-0"])
    collection.upsert(ids=["1-0"], documents=["old policy"], embeddings=[[1.0, 0.0]],
                      metadatas=[{"doc_id": 1, "filename": "policy.md", "chunk_index": 0}])
    doc.content = None
    await ingest.backfill_content()
    assert doc.content == "old policy"
    assert collection.get()["metadatas"][0]["index_version"] == "legacy"
    assert [c.text for c in await retriever.retrieve("policy")] == ["old policy"]


@pytest.mark.parametrize("size", [1, 3, 9, 100])
async def test_answer_never_emits_unredacted_tokens(monkeypatch, size):
    raw = "手机 13800001234，邮箱 alice.smith@example.com。"

    async def stream(messages):
        for start in range(0, len(raw), size):
            yield AIMessageChunk(content=raw[start:start + size])

    llm = SimpleNamespace(astream=stream)
    events = []
    monkeypatch.setattr(graph_module.llm_service, "chat", lambda *a, **kw: llm)
    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: events.append)
    monkeypatch.setattr(graph_module, "_record", AsyncMock())
    ctx = RunContext(1, "test", UsageCallback(1))
    result = await graph_module.answer({"query": "联系方式"}, {"configurable": {"ctx": ctx}})
    emitted = "".join(e["content"] for e in events if e["type"] == "token")
    assert emitted == result["answer"] == graph_module.redact(raw)
    assert "13800001234" not in emitted and "alice.smith@" not in emitted


async def test_followup_uses_history_and_standalone_query(monkeypatch):
    llm = Mock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content=json.dumps({
        "intent": "order_inquiry", "order_id": 123, "standalone_query": "订单123什么时候发货？"})))
    llm.bind_tools.return_value = llm
    monkeypatch.setattr(graph_module.llm_service, "chat", lambda *a, **kw: llm)
    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: lambda e: None)
    monkeypatch.setattr(graph_module, "_record", AsyncMock())
    retrieve = AsyncMock(return_value=[])
    monkeypatch.setattr(graph_module, "retrieve", retrieve)
    state = {"query": "那什么时候发货？", "history": [{"role": "user", "content": "查一下订单123"}]}
    config = {"configurable": {"ctx": RunContext(1, "test", UsageCallback(1))}}
    state.update(await graph_module.classify_intent(state, config))
    assert any(m.content == "查一下订单123" for m in llm.ainvoke.call_args.args[0])
    await graph_module.retrieve_node(state, config)
    retrieve.assert_awaited_once_with("订单123什么时候发货？")
    llm.ainvoke.return_value = AIMessage(content="DONE")
    await graph_module.call_tools(state, config)
    tool_messages = llm.ainvoke.call_args.args[0]
    assert any("订单123什么时候发货？" in m.content for m in tool_messages)
    assert any(m.content == "查一下订单123" for m in tool_messages)


@pytest.mark.parametrize("approved", [True, False])
async def test_actual_graph_interrupt_event_and_resume(monkeypatch, approved):
    async def classify(state, config):
        return {"intent": "order_inquiry", "order_id": 123}

    async def empty(state, config):
        return {}

    async def answer(state, config):
        return {"answer": "test answer"}

    calls = []

    async def ticket(state, config):
        if not state.get("error"):
            calls.append("ticket")
            return {"ticket_id": 7}
        return {}

    for name, node in [("classify_intent", classify), ("retrieve_node", empty), ("call_tools", empty),
                       ("answer", answer), ("create_ticket", ticket), ("notify", empty)]:
        monkeypatch.setattr(graph_module, name, node)
    monkeypatch.setattr(graph_module, "get_settings", lambda: SimpleNamespace(require_human_confirm=True))
    monkeypatch.setattr(runner, "graph", graph_module.build_graph())
    run = SimpleNamespace()
    monkeypatch.setattr(runner, "SessionLocal", lambda: Session({(AgentRun, 1): run}))
    monkeypatch.setattr(runner, "set_run_status", AsyncMock())
    ctx = RunContext(1, "test", UsageCallback(1))
    config = {"configurable": {"thread_id": "regression", "ctx": ctx}}
    events = [json.loads(e["data"]) async for e in runner._stream(
        1, ctx, {"query": "订单123", "history": []}, config, time.perf_counter(), None, "订单123")]
    assert events[-1]["type"] == "interrupt"
    assert events[-1]["run_id"] == 1
    assert run.status == "waiting_confirm" and calls == []
    resumed = [json.loads(e["data"]) async for e in runner._stream(
        1, ctx, Command(resume=approved), config, time.perf_counter(), None, "订单123")]
    assert resumed[-1]["type"] == "done"
    assert calls == (["ticket"] if approved else [])


async def test_expired_context_restores_db_history_in_order(monkeypatch):
    redis = SimpleNamespace(lrange=AsyncMock(return_value=[]), eval=AsyncMock())
    session = Session(rows=[SimpleNamespace(role="assistant", content="退货政策"),
                            SimpleNamespace(role="user", content="耳机怎么退货")])
    monkeypatch.setattr(memory, "get_redis", lambda: redis)
    monkeypatch.setattr(memory, "SessionLocal", lambda: session)
    assert await memory.get_context(2) == [
        {"role": "user", "content": "耳机怎么退货"}, {"role": "assistant", "content": "退货政策"}]
    redis.eval.assert_awaited_once()
    statement = str(session.scalars.call_args.args[0])
    assert "conversation_id" in statement and "DESC" in statement and "LIMIT" in statement


async def test_cached_context_does_not_read_db(monkeypatch):
    redis = SimpleNamespace(lrange=AsyncMock(return_value=['{"role":"user","content":"cached"}']))
    db = Mock(side_effect=AssertionError("Unexpected DB access"))
    monkeypatch.setattr(memory, "get_redis", lambda: redis)
    monkeypatch.setattr(memory, "SessionLocal", db)
    assert await memory.get_context(2) == [{"role": "user", "content": "cached"}]
    db.assert_not_called()


async def test_stale_task_does_not_overwrite_later_edit(index):
    collection, doc, _ = index
    doc.content = "latest edit"
    await ingest.ingest_text(1, "new policy")
    assert doc.content == "latest edit" and doc.index_version == "legacy"
    assert collection.get()["documents"] == ["old policy"]


async def test_cleanup_failure_keeps_published_version_searchable(monkeypatch, index):
    collection, doc, _ = index
    monkeypatch.setattr(collection, "delete", Mock(side_effect=RuntimeError("cleanup unavailable")))
    await ingest.ingest_text(1, "new policy")
    assert doc.status == "ready"
    assert collection.count() == 2
    assert [c.text for c in await retriever.retrieve("policy")] == ["new policy"]


async def test_migration_does_not_promote_abandoned_staged_chunks(index):
    collection, doc, _ = index
    doc.content = None
    collection.upsert(ids=["abandoned"], documents=["unfinished edit"], embeddings=[[1.0, 0.0]],
                      metadatas=[{"doc_id": 1, "filename": "policy.md", "chunk_index": 0,
                                  "index_version": "abandoned"}])
    await ingest.backfill_content()
    assert doc.content == "old policy"
    assert [c.text for c in await retriever.retrieve("policy")] == ["old policy"]
    assert collection.get(ids=["abandoned"])["metadatas"][0]["index_version"] == "abandoned"


async def test_run_reads_history_before_adding_current_message(monkeypatch):
    session = Session({(Conversation, 2): SimpleNamespace(user_id=1)})

    async def history(cid):
        session.add.assert_not_called()
        return [{"role": "user", "content": "previous question"}]

    def add(value):
        if isinstance(value, AgentRun):
            value.id = 987

    async def stream(run_id, ctx, payload, *args):
        assert payload["history"] == [{"role": "user", "content": "previous question"}]
        assert payload["query"] == "current question"
        yield {"event": "done", "data": '{"type":"done"}'}

    session.add.side_effect = add
    monkeypatch.setattr(runner, "SessionLocal", lambda: session)
    monkeypatch.setattr(runner, "get_context", history)
    monkeypatch.setattr(runner, "push_context", AsyncMock())
    monkeypatch.setattr(runner, "set_run_status", AsyncMock())
    monkeypatch.setattr(runner, "_stream", stream)
    monkeypatch.setattr(runner, "_contexts", {})
    events = [e async for e in runner.run_agent("current question", 2, "test", user_id=1)]
    assert json.loads(events[0]["data"])["conversation_id"] == 2
    assert events[-1]["event"] == "done"
