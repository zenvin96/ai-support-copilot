"""LangChain 回调：记录每次 LLM 调用的 token / 延迟 / 成本，落 llm_calls 表。"""
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from app.db.models import LlmCall
from app.db.session import SessionLocal


class UsageCallback(AsyncCallbackHandler):
    def __init__(self, run_id: int | None = None):
        self.run_id = run_id
        self.provider = None
        self._start: dict[UUID, float] = {}
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost_usd = 0.0
        self.calls = 0

    async def on_chat_model_start(self, serialized, messages, *, run_id: UUID, **kw: Any) -> None:
        self._start[run_id] = time.perf_counter()

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kw: Any) -> None:
        latency = int((time.perf_counter() - self._start.pop(run_id, time.perf_counter())) * 1000)
        usage = {}
        model = ""
        try:
            gen = response.generations[0][0]
            msg = getattr(gen, "message", None)
            usage = (getattr(msg, "usage_metadata", None) or {}) if msg else {}
            model = (getattr(msg, "response_metadata", {}) or {}).get("model_name", "")
        except (IndexError, AttributeError):
            pass
        if not usage:
            usage = (response.llm_output or {}).get("token_usage", {}) or {}
            model = model or (response.llm_output or {}).get("model_name", "")
        p = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        c = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        cost = self.provider.cost(model, p, c) if self.provider else 0.0
        self.prompt_tokens += p
        self.completion_tokens += c
        self.cost_usd += cost
        self.calls += 1
        async with SessionLocal() as db:
            db.add(LlmCall(run_id=self.run_id, provider=self.provider.name if self.provider else "?",
                           model=model, prompt_tokens=p, completion_tokens=c,
                           latency_ms=latency, cost_usd=cost))
            await db.commit()

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
