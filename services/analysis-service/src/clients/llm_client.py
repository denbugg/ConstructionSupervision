"""Клиент LLM по OpenAI-совместимому API (`POST {LLM_BASE_URL}/chat/completions`).

Так говорят и облачные провайдеры, и локальные серверы — llama.cpp (`llama-server`),
Ollama, vLLM, поэтому смена модели — это `LLM_BASE_URL`, `LLM_MODEL` и ключ в `.env`, а не
код. Повторов нет: недоступная модель — сразу шаблонное резюме (architecture.md, раздел 6).
"""

from typing import Any

import httpx
from lct_common import get_logger

log = get_logger(__name__)
# Ответ по фактам, а не творчество: низкая температура делает текст ближе к контексту.
TEMPERATURE = 0.2
# Резюме — до 120 слов; запас на русский текст в токенах.
MAX_TOKENS = 700


class LlmUnavailable(Exception):
    """Модель не ответила или ответила не по контракту; причина — в тексте исключения."""


class LlmClient:
    def __init__(self, base_url: str, model: str, api_key: str, timeout_s: float) -> None:
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout_s, headers=headers
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete(self, system: str, user: str) -> str:
        """Текст ответа модели на пару «инструкция + контекст»."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
        }
        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPError as exc:
            raise LlmUnavailable(type(exc).__name__) from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmUnavailable("ответ не по контракту OpenAI") from exc
        if not isinstance(content, str):
            raise LlmUnavailable("в ответе нет текста")
        return content
