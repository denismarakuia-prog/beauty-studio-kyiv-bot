"""OpenAI-powered assistant with retry, timeout and fallback support."""
from __future__ import annotations

import asyncio
import logging
from itertools import cycle
from typing import Optional

from bot.salon_data import (
    SALON_ADDRESS,
    SALON_HOURS,
    SALON_NAME,
    SALON_PHONES,
    SERVICES,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = f"""Ти — професійний та доброзичливий адміністратор салону краси «{SALON_NAME}».

Інформація про салон:
• Назва: {SALON_NAME}
• Адреса: {SALON_ADDRESS}
• Телефони: {", ".join(SALON_PHONES)}
• Години роботи: {SALON_HOURS}
• Послуги:
{chr(10).join(f"  – {s.emoji} {s.name}: {s.price}, {s.duration}" for s in SERVICES)}

Правила спілкування:
1. Відповідай ВИКЛЮЧНО українською мовою.
2. Відповідь — 3–5 речень максимум.
3. Тон: тепло-професійний, як у реального адміністратора.
4. При будь-якій нагоді ненав'язливо пропонуй записатися.
5. Не вигадуй інформацію, якої немає в описі вище.
6. Якщо питання не стосується салону — м'яко переводь тему на послуги."""

_FALLBACKS = cycle([
    "Вибачте, зараз виникли технічні труднощі. Ви можете зателефонувати нам або натиснути «📅 Записатися» — ми будемо раді вам допомогти! 💕",
    "На жаль, наразі не можу відповісти. Зателефонуйте нам або залиште заявку через кнопку «Записатися» — і ми одразу зв'яжемося! ✨",
    "Технічна помилка з мого боку. Будь ласка, зв'яжіться з нами по телефону або оберіть «📅 Записатися» нижче 💅",
])


class AIService:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._model = model
        self._enabled = bool(api_key)
        if self._enabled:
            try:
                from openai import AsyncOpenAI  # noqa: PLC0415
                self._client: Optional[AsyncOpenAI] = AsyncOpenAI(
                    api_key=api_key, timeout=20.0
                )
            except Exception as exc:
                logger.error("Failed to initialise OpenAI client: %s", exc)
                self._enabled = False
                self._client = None
        else:
            self._client = None
            logger.warning("OPENAI_API_KEY is not set — AI assistant disabled.")

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def ask(self, question: str) -> str:
        if not self._enabled or self._client is None:
            return (
                "Функція AI-асистента наразі недоступна. "
                "Ви можете зателефонувати нам або натиснути «📅 Записатися» 💕"
            )

        for attempt in range(3):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": question[:1000]},
                    ],
                    max_tokens=300,
                    temperature=0.75,
                )
                content = response.choices[0].message.content
                return (content or "").strip() or next(_FALLBACKS)

            except Exception as exc:
                exc_name = type(exc).__name__
                logger.warning("OpenAI attempt %d failed (%s): %s", attempt + 1, exc_name, exc)
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))

        return next(_FALLBACKS)
