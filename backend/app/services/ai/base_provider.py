from abc import ABC, abstractmethod


class BaseAIProvider(ABC):
    provider_name: str

    @abstractmethod
    def translate(self, prompt: str) -> str:
        raise NotImplementedError