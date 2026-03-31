from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        raise NotImplementedError
