from api.integrations.llm.base import BaseLLMClient


class MockOpenAIClient(BaseLLMClient):
    def complete(self, prompt: str) -> str:
        return f"Mock completion for prompt: {prompt[:120]}"
