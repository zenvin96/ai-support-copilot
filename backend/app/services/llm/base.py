"""LLM Provider 抽象。新增厂商只需实现 build() 并注册到 PROVIDERS。"""
from abc import ABC, abstractmethod

from langchain_core.language_models import BaseChatModel


class LlmProvider(ABC):
    name: str
    models: tuple[str, ...]
    # USD / 1M tokens: (prompt, completion)
    prices: dict[str, tuple[float, float]]

    @abstractmethod
    def build(self, model: str, temperature: float = 0.0, streaming: bool = False) -> BaseChatModel: ...

    def supports(self, model: str) -> bool:
        return model in self.models

    def cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        p_in, p_out = self.prices.get(model, (0.0, 0.0))
        return (prompt_tokens * p_in + completion_tokens * p_out) / 1_000_000
