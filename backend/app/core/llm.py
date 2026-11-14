"""LLM Client using OpenAI SDK with pydanctic validation."""


from openai import AsyncOpenAI
from pydantic import BaseModel

class LLMClient:
    """Using OpenAI SDK."""
    def __init__(self, api_key: str, model: str) -> None:
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self.model = model
    
    async def generate_structured[T: BaseModel](
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        completion = await self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_model,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError(f"OpenAI failed to parse response into {response_model.__name__}")
        return parsed