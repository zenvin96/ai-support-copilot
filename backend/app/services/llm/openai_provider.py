from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.services.llm.base import LlmProvider


class OpenAIProvider(LlmProvider):
    """OpenAI 官方或任何 OpenAI 兼容中转站（OPENAI_BASE_URL）。"""
    name = "openai"
    prices = {"gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.50, 10.0), "gpt-4.1-mini": (0.40, 1.60),
              "gpt-4.1": (2.0, 8.0), "gpt-5-mini": (0.25, 2.0)}

    @property
    def models(self) -> tuple[str, ...]:  # type: ignore[override]
        custom = get_settings().openai_models
        return tuple(m.strip() for m in custom.split(",") if m.strip()) if custom else ("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini")

    def build(self, model: str, temperature: float = 0.0, streaming: bool = False) -> BaseChatModel:
        s = get_settings()
        return ChatOpenAI(model=model, temperature=temperature, streaming=streaming, api_key=s.openai_api_key,
                          base_url=s.openai_base_url or None, stream_usage=True)


class DeepSeekProvider(LlmProvider):
    """DeepSeek 兼容 OpenAI 协议，只换 base_url。"""
    name = "deepseek"
    # deepseek-flash = V4.1 Flash，deepseek-v4-pro = V4 Pro；价格为峰值价（USD / 1M tokens，缓存未命中）
    models = ("deepseek-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner")
    prices = {"deepseek-flash": (0.30, 1.20), "deepseek-v4-pro": (1.32, 3.96),
              "deepseek-chat": (0.27, 1.10), "deepseek-reasoner": (0.55, 2.19)}

    def build(self, model: str, temperature: float = 0.0, streaming: bool = False) -> BaseChatModel:
        return ChatOpenAI(model=model, temperature=temperature, streaming=streaming,
                          api_key=get_settings().deepseek_api_key,
                          base_url="https://api.deepseek.com/v1", stream_usage=True)
