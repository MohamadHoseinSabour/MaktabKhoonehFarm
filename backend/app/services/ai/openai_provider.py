from openai import OpenAI

from app.services.ai.base_provider import BaseAIProvider


class OpenAIProvider(BaseAIProvider):
    provider_name = 'openai'

    def __init__(self, api_key: str, model: str, endpoint_url: str | None = None) -> None:
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=endpoint_url)

    def translate(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            temperature=0.2,
        )
        return response.output_text.strip()