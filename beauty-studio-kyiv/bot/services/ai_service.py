"""
AI assistant with three layers, in order:
  1. OpenAI (if a key is configured), with retries.
  2. A salon knowledge base — keyword-matched answers built directly from
     salon_data.py (services, prices, hours, address, phones). Keyword lists
     deliberately mix Ukrainian, Russian, and common surzhyk spellings,
     since clients write in whichever feels natural to them — matching is
     purely on the INPUT side, the bot's own replies always stay in
     Ukrainian. This is what guarantees normal salon questions are ALWAYS
     answered correctly even if OpenAI is completely unavailable
     (wrong/expired key, no network egress, quota exhausted, etc.).
  3. A soft, still-helpful, ROTATING generic nudge — only reached for
     genuinely unrecognised/off-topic input, never for a real salon
     question, and never the exact same wording twice in a row.
"""
from __future__ import annotations

import asyncio
import logging
from itertools import cycle
from typing import Dict, List, Optional

from bot.salon_data import (
    SALON_ABOUT,
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
1. Незалежно від мови запитання (українська, російська, суржик) — відповідай ВИКЛЮЧНО українською мовою.
2. Відповідь — 3–5 речень максимум.
3. Тон: тепло-професійний, як у реального адміністратора.
4. При будь-якій нагоді ненав'язливо пропонуй записатися.
5. Не вигадуй інформацію, якої немає в описі вище.
6. Якщо питання не стосується салону — м'яко переводь тему на послуги."""


# ── Salon knowledge base (OpenAI-independent fallback) ──────────────────────────

_SERVICE_SYNONYMS: Dict[str, List[str]] = {
    "manicure":    ["манікюр", "маникюр"],
    "pedicure":    ["педикюр"],
    "haircut":     ["стрижка", "стрижку", "стрижки", "підстригти", "подстричь", "постричься"],
    "coloring":    ["фарбування", "фарбувати", "окрашивание", "покраска", "покрасить",
                     "краска волос", "пофарбувати"],
    "cosmetology": ["косметологія", "косметология", "чистка обличчя", "чистка лица",
                     "пілінг", "пилинг"],
}

_PRICE_KW = (
    "ціна", "цін", "прайс", "коштує", "вартість", "скільки",
    "цена", "стоит", "стоимост", "сколько", "почем",
)

_HOURS_KW = (
    "час роботи", "графік", "коли працю", "відкрит", "закрит", "робочі години",
    "до якої", "з якої",
    "часы работы", "график", "когда работа", "когда вы работ", "открыт", "закрыт",
    "рабочие часы", "до которого", "со скольки", "до скольки",
)

_ADDRESS_KW = (
    "адрес", "де ви", "де знаходит", "локац", "як доїхати", "де салон", "де ти",
    "где вы", "где находит", "как доехать",
)

_PHONE_KW = (
    "телефон", "номер", "зв'язатися", "зателефонувати", "контакт",
    "связаться", "позвонить", "позвонити",
)

_BOOKING_KW = (
    "запис", "забронюва", "хочу прийти", "можна прийти", "вільний час",
    "вільне місце", "вільн",
    "запись", "забронировать", "свободное время", "свободно", "свободн",
    "можно прийти", "хочу записаться",
)

_ABOUT_KW = (
    "хто ви", "про салон", "розкажіть про", "історія", "давно працю",
    "кто вы", "о салоне", "расскажите о", "история", "давно работа",
)

_GREETING_KW = (
    "привіт", "добрий день", "вітаю", "доброго дня",
    "привет", "добрый день", "здравствуйте", "хай",
    "hi", "hello",
)


def _knowledge_base_answer(question: str) -> Optional[str]:
    q = question.lower()

    # Specific service mentioned -> its own detailed card (checked first, most specific)
    for svc in SERVICES:
        synonyms = _SERVICE_SYNONYMS.get(svc.id, [svc.name.lower()])
        if any(syn in q for syn in synonyms):
            return (
                f"{svc.emoji} <b>{svc.name}</b>\n\n"
                f"{svc.description}\n\n"
                f"⏱ Тривалість: {svc.duration}\n"
                f"💰 Вартість: {svc.price}\n\n"
                "Натисніть «📅 Записатися», щоб обрати дату й час! 💕"
            )

    if any(kw in q for kw in _PRICE_KW):
        lines = [f"💰 <b>Прайс-лист — {SALON_NAME}</b>\n"]
        for s in SERVICES:
            lines.append(f"{s.emoji} {s.name}: {s.price}")
        lines.append("\nНатисніть «💰 Прайс» у меню, щоб побачити деталі!")
        return "\n".join(lines)

    if any(kw in q for kw in _HOURS_KW):
        return f"🕐 Ми працюємо: <b>{SALON_HOURS}</b>\n\nЧекаємо на вас! 💕"

    if any(kw in q for kw in _ADDRESS_KW):
        return f"📍 Ми знаходимось:\n<b>{SALON_ADDRESS}</b>\n\nБудемо раді бачити вас! 💕"

    if any(kw in q for kw in _PHONE_KW):
        phones = "\n".join(f"📞 {p}" for p in SALON_PHONES)
        return f"Зв'яжіться з нами:\n{phones}\n\nАбо просто натисніть «📅 Записатися»! 💕"

    if any(kw in q for kw in _BOOKING_KW):
        return (
            "Звичайно! Натисніть кнопку «📅 Записатися» в меню нижче — "
            "оберете послугу, дату й час за кілька секунд! ✨"
        )

    if any(kw in q for kw in _ABOUT_KW):
        return f"ℹ️ <b>{SALON_NAME}</b>\n\n{SALON_ABOUT}"

    if any(kw in q for kw in _GREETING_KW):
        return (
            f"Привіт! 👋 Раді бачити вас у {SALON_NAME}!\n\n"
            "Запитайте про послуги, ціни або натисніть «📅 Записатися», "
            "щоб обрати час візиту 💕"
        )

    return None


# Several distinct phrasings, rotated — guarantees a genuinely unrecognised
# question is never met with the exact same canned line every single time.
_GENERIC_NUDGES = cycle([
    "На жаль, я не знайшов точної відповіді на ваше запитання 🙏\n\n"
    "Спробуйте кнопки меню — «💰 Прайс», «📍 Контакти» — або натисніть "
    "«📅 Записатися», і наш майстер відповість особисто! 💕",

    "Хм, не зовсім зрозумів(ла) питання 🙂 Можливо, вас цікавлять послуги, "
    "ціни чи графік роботи? Або просто натисніть «📅 Записатися» — "
    "адміністратор детально все розповість! ✨",

    "Вибачте, я спеціалізуюсь саме на питаннях про салон 💅 Запитайте про "
    "послуги, прайс чи контакти — або скористайтеся кнопками меню нижче 👇",
])


class AIService:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._model = model
        self._enabled = bool(api_key)
        self._client = None
        if self._enabled:
            try:
                from openai import AsyncOpenAI  # noqa: PLC0415
                self._client = AsyncOpenAI(api_key=api_key, timeout=20.0)
                logger.info("AI assistant: OpenAI client initialised (model=%s).", model)
            except Exception as exc:
                logger.error("Failed to initialise OpenAI client: %s", exc)
                self._enabled = False
        else:
            logger.warning(
                "OPENAI_API_KEY is not set — AI assistant will use the salon "
                "knowledge base only (no live OpenAI calls)."
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def ask(self, question: str) -> str:
        if self._enabled and self._client is not None:
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
                    answer = (content or "").strip()
                    if answer:
                        return answer
                    logger.warning("OpenAI returned an empty answer — using knowledge base.")
                    break
                except Exception as exc:
                    exc_name = type(exc).__name__
                    logger.warning(
                        "OpenAI attempt %d/3 failed (%s): %s", attempt + 1, exc_name, exc
                    )
                    if attempt < 2:
                        await asyncio.sleep(1.5 * (attempt + 1))
            else:
                logger.error(
                    "All OpenAI attempts failed for this question — "
                    "falling back to the salon knowledge base."
                )

        kb_answer = _knowledge_base_answer(question)
        if kb_answer:
            return kb_answer

        return next(_GENERIC_NUDGES)
