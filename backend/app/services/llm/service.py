"""统一入口：按 model 名路由到 Provider，并挂上用量回调。"""
import asyncio

from langchain_core.language_models import BaseChatModel
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.services.llm.base import LlmProvider
from app.services.llm.openai_provider import DeepSeekProvider, OpenAIProvider
from app.services.usage.tracker import UsageCallback

PROVIDERS: list[LlmProvider] = [OpenAIProvider(), DeepSeekProvider()]


class LlmService:
    def provider_for(self, model: str) -> LlmProvider:
        for p in PROVIDERS:
            if p.supports(model):
                return p
        raise ValueError(f"unknown model: {model}")

    def available_models(self) -> list[dict]:
        s = get_settings()
        out = []
        for p in PROVIDERS:
            configured = bool(getattr(s, f"{p.name}_api_key"))
            out += [{"provider": p.name, "model": m, "configured": configured} for m in p.models]
        return out

    def chat(self, model: str | None = None, *, temperature: float = 0.0,
             streaming: bool = False, usage: UsageCallback | None = None) -> BaseChatModel:
        model = model or get_settings().default_model
        provider = self.provider_for(model)
        llm = provider.build(model, temperature=temperature, streaming=streaming)
        if usage is not None:
            usage.provider = provider
            llm = llm.with_config(callbacks=[usage])
        return llm

    async def embed(self, texts: list[str]) -> list[list[float]]:
        s = get_settings()
        if s.embedding_provider == "local":
            return await asyncio.to_thread(_local_embed, texts)
        client = AsyncOpenAI(api_key=s.openai_api_key, base_url=s.openai_base_url or None)
        resp = await client.embeddings.create(model=s.embedding_model, input=texts)
        return [d.embedding for d in resp.data]


_local_model = None


def _local_embed(texts: list[str]) -> list[list[float]]:
    """本地 embedding：fastembed（ONNX），首次调用下载模型到 FASTEMBED_CACHE_PATH。"""
    global _local_model
    if _local_model is None:
        from fastembed import TextEmbedding

        _local_model = TextEmbedding(model_name=get_settings().local_embedding_model)
    return [v.tolist() for v in _local_model.embed(texts)]


llm_service = LlmService()
