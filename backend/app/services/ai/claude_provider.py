from app.services.ai.base_provider import BaseAIProvider


class ClaudeProvider(BaseAIProvider):
    provider_name = 'claude'

    def __init__(self, api_key: str, model: str, endpoint_url: str | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.endpoint_url = endpoint_url

    def translate(self, prompt: str) -> str:
        raise NotImplementedError('Claude provider is scaffolded but not wired to SDK yet.')