"""Резюме отчёта: текст нейросети, прошедший проверку чисел, иначе — шаблон (ADR-0008).

Шаблонное резюме строится всегда: оно и запасной вариант, и то, что получит отчёт при
выключенной, недоступной или ошибившейся модели. Причина отказа от текста модели попадает
в подпись источника — читатель отчёта видит, почему резюме шаблонное.
"""

from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from lct_common import get_logger

from src.clients.llm_client import LlmClient, LlmUnavailable
from src.config import settings
from src.report.html import Summary, template_summary
from src.report.summary import check_summary, clean_text, context_json, llm_context
from src.services.runs import SERVICE_ROOT

log = get_logger(__name__)
LLM = "LLM"


@lru_cache
def prompt() -> str:
    path = Path(settings.llm_prompt_file)
    return (path if path.is_absolute() else SERVICE_ROOT / path).read_text(encoding="utf-8")


class Summarizer:
    def __init__(self, client: LlmClient | None) -> None:
        # None — модель выключена (`LLM_ENABLED=false`) или не настроена (`LLM_BASE_URL`).
        self._client = client

    async def summarize(self, context: dict[str, Any]) -> tuple[Summary, list[str]]:
        """Резюме и причины, по которым текст модели отброшен (пусто — не отбрасывали).

        В подпись источника — в том числе в PDF — причины идут общими словами: выдуманному
        числу не место в отчёте даже в пояснении. Конкретика — в журнале и в ответе API.
        """
        template = template_summary(context)
        if self._client is None:
            return template, []
        facts = llm_context(context)
        try:
            raw = await self._client.complete(
                prompt(), f"Факты отчёта (JSON):\n{context_json(facts)}"
            )
        except LlmUnavailable as exc:
            log.warning("summary.llm_unavailable", reason=str(exc))
            return replace(template, source=f"{template.source}: нейросеть недоступна"), [
                f"нейросеть недоступна: {exc}"
            ]
        text = clean_text(raw)
        problems = check_summary(text, facts)
        if problems:
            # Отброшенный текст — в журнал: по нему правят промпт, а не догадываются.
            log.warning("summary.llm_rejected", problems=problems, text=text)
            source = f"{template.source}: текст нейросети не прошёл проверку чисел и ссылок"
            return replace(template, source=source), problems
        source = f"нейросеть {self._client.model}; каждое число сверено с фактами отчёта"
        return Summary(text=text, generated_by=LLM, source=source), []
