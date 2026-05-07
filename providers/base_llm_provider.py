from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(slots=True)
class ProviderResponse:
    text: str

    def __iter__(self):
        yield self


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    provider: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


class BaseLLMProvider(ABC):
    name: str

    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_models(
        self,
        configured_models: list[str],
        *,
        preferred_model: Optional[str] = None,
    ) -> list[ModelCandidate]:
        raise NotImplementedError

    @abstractmethod
    def invoke(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        generation_config: Optional[dict],
        request_options: Optional[dict],
    ) -> ProviderResponse:
        raise NotImplementedError
