from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings


class VertexClient:
    MODEL_NAME = "gemini-2.5-flash"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, prompt: str) -> str:
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": self.settings.model_temperature,
                "maxOutputTokens": self.settings.model_max_output_tokens,
            },
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.settings.google_api_key,
        }
        params = {"key": self.settings.google_api_key}

        last_error: RuntimeError | None = None
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            for url in self._generate_urls():
                response = await client.post(url, json=payload, headers=headers, params=params)
                if response.status_code >= 400:
                    last_error = RuntimeError(
                        f"Vertex API error {response.status_code}: {response.text[:400]}"
                    )
                    continue

                data = response.json()
                text = _extract_text(data)
                if text:
                    return text
                last_error = RuntimeError("Vertex API returned empty response")

        if last_error:
            raise last_error
        raise RuntimeError("Vertex API request failed for unknown reason")

    def _generate_urls(self) -> list[str]:
        model_path = f"publishers/google/models/{self.MODEL_NAME}"
        return [f"https://aiplatform.googleapis.com/v1/{model_path}:generateContent"]


def _extract_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = (
        ((candidates[0] or {}).get("content") or {}).get("parts") or []
    )
    result: list[str] = []
    for part in parts:
        text = (part or {}).get("text")
        if text:
            result.append(text)
    return "\n".join(result).strip()
