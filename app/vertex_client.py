from __future__ import annotations

import asyncio

from google import genai
from google.genai import types

from app.config import Settings


class VertexClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = genai.Client(
            vertexai=True,
            api_key=self.settings.google_api_key,
        )

    async def generate(self, prompt: str) -> str:
        return await asyncio.to_thread(self._generate_sync, prompt)

    def _generate_sync(self, prompt: str) -> str:
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            )
        ]
        tools = [types.Tool(google_search=types.GoogleSearch())]
        config = types.GenerateContentConfig(
            temperature=self.settings.model_temperature,
            top_p=1,
            max_output_tokens=self.settings.model_max_output_tokens,
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH",
                    threshold="OFF",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="OFF",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    threshold="OFF",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT",
                    threshold="OFF",
                ),
            ],
            tools=tools,
            thinking_config=types.ThinkingConfig(thinking_budget=-1),
        )

        chunks: list[str] = []
        for chunk in self._client.models.generate_content_stream(
            model=self.settings.vertex_model,
            contents=contents,
            config=config,
        ):
            if not getattr(chunk, "text", None):
                continue
            chunks.append(chunk.text)

        answer = "".join(chunks).strip()
        if not answer:
            raise RuntimeError("Vertex API returned empty response")
        return answer
