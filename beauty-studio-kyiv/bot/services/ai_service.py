"""
Multilingual (Ukrainian/Russian) AI salon assistant.

Architecture, in order, per message:
  1. Detect the message's language (UA/RU) from its own text — independent
     of the user's saved menu-language preference.
  2. Intent detection against a local, bilingual knowledge base built from
     salon_data.py. A confident match returns INSTANTLY — OpenAI is never
     called for a question we can already answer correctly, which is both
     faster and saves tokens.
  3. Only if nothing matched locally: a single short OpenAI call (no chat
     history, small system prompt, capped tokens) for genuinely open-ended
     questions.
  4. If OpenAI is unavailable/fails/returns nothing useful: fall back to
     the knowledge base's catch-all, varied so the same line never repeats
     twice in a row for the same user.

No new dependencies: language detection and typo-tolerance use only the
standard library (re, difflib, random) — no extra packages, no extra
database, nothing that would make this anything but a lightweight, fast,
Render-Free-friendly demo project.
"""
from __future__ import annotations

import asyncio
import difflib
import logging
import random
import re
from datetime import datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from bot.salon_data import (
    CURRENT_PROMOTIONS,
    SALON_ABOUT,
    SALON_ABOUT_RU,
    SALON_ADDRESS,
    SALON_HOURS,
    SALON_INSTAGRAM,
    SALON_NAME,
    SALON_PAYMENT_METHODS,
    SALON_PHONES,
    SALON_TELEGRAM_CHANNEL,
    SERVICES,
    SERVICES_MAP,
    TIMEZONE_NAME,
)

logger = logging.getLogger(__name__)

_TZ = ZoneInfo(TIMEZONE_NAME)


# ── Language detection (pure stdlib, no extra dependency) ───────────────────────

_UK_ONLY_CHARS = set("іїєґ")
_RU_ONLY_CHARS = set("ыэъё")

_UK_MARKER_WORDS = {
    "привіт", "вітаю", "дякую", "будь", "ласка", "скільки", "коли", "де",
    "як", "що", "це", "потрібно", "добрий", "добра", "доброго", "вечір",
    "ранок", "сьогодні", "завтра", "коштує", "вартість", "працюєте",
    "знаходитесь", "записатися", "запис", "вільно", "скасувати",
    "послуга", "послуги", "ціна", "ціни", "контакти", "адреса", "так",
    "ні", "майстер", "майстри", "будь-ласка", "дайте", "напишіть",
    "напишіт", "написати", "акції", "знижки",
}
_RU_MARKER_WORDS = {
    "привет", "здравствуйте", "спасибо", "пожалуйста", "сколько", "когда",
    "где", "как", "что", "это", "нужно", "добрый", "добрая", "доброе",
    "вечер", "утро", "сегодня", "завтра", "стоит", "стоимость",
    "работаете", "находитесь", "записаться", "запись", "свободно",
    "отменить", "услуга", "услуги", "цена", "цены", "контакты", "адрес",
    "братан", "брат", "норм", "дела", "нового", "написать", "акции",
    "скидки", "мастер", "мастера", "девушки", "ребят",
}


def detect_language(text: str) -> Optional[str]:
    """Best-effort UA/RU detection. Returns None if genuinely ambiguous
    (e.g. very short text with no distinguishing characters or words)."""
    if not text:
        return None
    low = text.lower()

    uk_chars = sum(1 for c in low if c in _UK_ONLY_CHARS)
    ru_chars = sum(1 for c in low if c in _RU_ONLY_CHARS)
    if uk_chars or ru_chars:
        return "uk" if uk_chars >= ru_chars else "ru"

    words = set(re.findall(r"[а-яёіїєґ]+", low))
    uk_score = len(words & _UK_MARKER_WORDS)
    ru_score = len(words & _RU_MARKER_WORDS)
    if uk_score == ru_score == 0:
        return None
    return "uk" if uk_score >= ru_score else "ru"


# ── Typo-tolerant keyword matching (difflib, stdlib only) ───────────────────────

def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zа-яёіїєґ']+", text.lower())


def _matches(message_lower: str, words: List[str], keywords: List[str]) -> bool:
    # Fast path: phrase/substring match (also catches exact single words).
    if any(kw in message_lower for kw in keywords):
        return True
    # Typo-tolerant path: only meaningful for single-word keywords of
    # reasonable length (fuzzy-matching very short words is too noisy).
    # A similarity cutoff alone isn't enough to separate genuine typos
    # ("коштує"/"коштуе", "манікюр"/"манікюq") from unrelated words that
    # merely share a long common prefix ("привет"/"привести" scores 0.86 —
    # higher than some real typos do) — both can land in the same ratio
    # band. Requiring the candidate to be within 1 character of the
    # keyword's length cleanly separates the two: real typos are
    # same-length or off-by-one; "привести" is two characters longer than
    # "привет" and gets correctly rejected.
    single_word = [kw for kw in keywords if " " not in kw and len(kw) >= 4]
    if not single_word or not words:
        return False
    for kw in single_word:
        candidates = [w for w in words if abs(len(w) - len(kw)) <= 1]
        if not candidates:
            continue
        if difflib.get_close_matches(kw, candidates, n=1, cutoff=0.82):
            return True
    return False


# ── Varied, non-repeating responses ─────────────────────────────────────────────
#
# Plain in-memory dict (no new database) tracking the last fallback line
# shown to each user, so the assistant never repeats itself back-to-back.

_last_shown: Dict[int, str] = {}
_LAST_SHOWN_MAX_ENTRIES = 50_000  # same bound used by ThrottlingMiddleware, for consistency


def _pick(options: List[str], user_id: int) -> str:
    if len(options) == 1:
        return options[0]
    last = _last_shown.get(user_id)
    choices = [o for o in options if o != last] or options
    pick = random.choice(choices)
    _last_shown[user_id] = pick
    if len(_last_shown) > _LAST_SHOWN_MAX_ENTRIES:
        oldest = next(iter(_last_shown))
        del _last_shown[oldest]
    return pick


# ── Knowledge base content (bilingual) ──────────────────────────────────────────

def _service_card(service_id: str, lang: str) -> Optional[str]:
    svc = SERVICES_MAP.get(service_id)
    if not svc:
        return None
    if lang == "ru":
        return (
            f"{svc.emoji} <b>{svc.name_for('ru')}</b>\n\n"
            f"{svc.description_for('ru')}\n\n"
            f"⏱ Длительность: {svc.duration}\n"
            f"💰 Стоимость: {svc.price}\n\n"
            "Нажмите «📅 Записаться», чтобы выбрать дату и время! 💕"
        )
    return (
        f"{svc.emoji} <b>{svc.name_for('uk')}</b>\n\n"
        f"{svc.description_for('uk')}\n\n"
        f"⏱ Тривалість: {svc.duration}\n"
        f"💰 Вартість: {svc.price}\n\n"
        "Натисніть «📅 Записатися», щоб обрати дату й час! 💕"
    )


_SERVICE_SYNONYMS: Dict[str, List[str]] = {
    "manicure":    ["манікюр", "маникюр"],
    "pedicure":    ["педикюр"],
    "haircut":     ["стрижка", "стрижку", "стрижки", "підстригти", "подстричь", "постричься", "волосся", "волосы"],
    "coloring":    ["фарбування", "фарбувати", "окрашивание", "покраска", "покрасить",
                     "краска", "пофарбувати", "колорист"],
    "cosmetology": ["косметологія", "косметология", "чистка", "пілінг", "пилинг", "мезотерапія", "мезотерапия"],
}

# Recognised but NOT configured as a real bookable service — answer honestly
# instead of inventing prices, per "do not invent information" principle.
_UNCONFIGURED_SERVICE_KEYWORDS = [
    "брови", "брова", "брів", "eyebrow",
    "вії", "ресниц", "ресницы", "eyelash", "ламінування вій", "ламинирование ресниц",
    "масаж", "массаж", "massage",
]


def _price_list(lang: str) -> str:
    if lang == "ru":
        lines = [f"💰 <b>Прайс-лист — {SALON_NAME}</b>\n"]
        for s in SERVICES:
            lines.append(f"{s.emoji} {s.name_for('ru')}: {s.price}")
        lines.append("\nНажмите «💰 Цены» в меню, чтобы увидеть подробности!")
        return "\n".join(lines)
    lines = [f"💰 <b>Прайс-лист — {SALON_NAME}</b>\n"]
    for s in SERVICES:
        lines.append(f"{s.emoji} {s.name_for('uk')}: {s.price}")
    lines.append("\nНатисніть «💰 Прайс» у меню, щоб побачити деталі!")
    return "\n".join(lines)


def _hours_text(lang: str) -> str:
    if lang == "ru":
        return f"🕐 Мы работаем: <b>{SALON_HOURS}</b>\n\nЖдём вас! 💕"
    return f"🕐 Ми працюємо: <b>{SALON_HOURS}</b>\n\nЧекаємо на вас! 💕"


def _address_text(lang: str) -> str:
    if lang == "ru":
        return f"📍 Мы находимся:\n<b>{SALON_ADDRESS}</b>\n\nБудем рады видеть вас! 💕"
    return f"📍 Ми знаходимось:\n<b>{SALON_ADDRESS}</b>\n\nБудемо раді бачити вас! 💕"


def _phones_text(lang: str) -> str:
    phones = "\n".join(f"📞 {p}" for p in SALON_PHONES)
    if lang == "ru":
        return f"Свяжитесь с нами:\n{phones}\n\nИли просто нажмите «📅 Записаться»! 💕"
    return f"Зв'яжіться з нами:\n{phones}\n\nАбо просто натисніть «📅 Записатися»! 💕"


def _booking_text(lang: str) -> str:
    if lang == "ru":
        return (
            "Конечно! Нажмите кнопку «📅 Записаться» в меню ниже — "
            "выберете услугу, дату и время за несколько секунд! ✨"
        )
    return (
        "Звичайно! Натисніть кнопку «📅 Записатися» в меню нижче — "
        "оберете послугу, дату й час за кілька секунд! ✨"
    )


def _my_booking_text(lang: str) -> str:
    if lang == "ru":
        return (
            "Чтобы посмотреть или отменить вашу запись — нажмите «📖 Моя запись» "
            "в меню ниже. А чтобы посмотреть свободное время — «📅 Записаться»! ✨"
        )
    return (
        "Щоб переглянути або скасувати свій запис — натисніть «📖 Мій запис» "
        "у меню нижче. А щоб побачити вільний час — «📅 Записатися»! ✨"
    )


def _cancellation_text(lang: str) -> str:
    if lang == "ru":
        return (
            "Отменить запись очень просто: откройте «📖 Моя запись» в меню "
            "и нажмите «❌ Отменить запись». Место сразу освободится для других клиентов 🙂"
        )
    return (
        "Скасувати запис дуже просто: відкрийте «📖 Мій запис» у меню "
        "і натисніть «❌ Скасувати запис». Місце одразу звільниться для інших клієнтів 🙂"
    )


def _about_text(lang: str) -> str:
    about = SALON_ABOUT_RU if lang == "ru" and SALON_ABOUT_RU else SALON_ABOUT
    title = f"ℹ️ <b>{SALON_NAME}</b>"
    return f"{title}\n\n{about}"


def _social_text(lang: str) -> str:
    handles = []
    if SALON_INSTAGRAM:
        handles.append(f"📷 Instagram: {SALON_INSTAGRAM}")
    if SALON_TELEGRAM_CHANNEL:
        handles.append(f"💬 Telegram: {SALON_TELEGRAM_CHANNEL}")
    if handles:
        body = "\n".join(handles)
        return (f"{body}\n\nПідписуйтесь! 💕" if lang == "uk" else f"{body}\n\nПодписывайтесь! 💕")
    if lang == "ru":
        phones = "\n".join(f"📞 {p}" for p in SALON_PHONES)
        return (
            "Актуальные ссылки на соцсети уточняйте, пожалуйста, по телефону:\n"
            f"{phones}\n\nС радостью поделимся! 💕"
        )
    phones = "\n".join(f"📞 {p}" for p in SALON_PHONES)
    return (
        "Актуальні посилання на соцмережі уточнюйте, будь ласка, за телефоном:\n"
        f"{phones}\n\nЗ радістю поділимось! 💕"
    )


def _payment_text(lang: str) -> str:
    if lang == "ru":
        return f"💳 Способы оплаты: <b>{SALON_PAYMENT_METHODS}</b>"
    return f"💳 Способи оплати: <b>{SALON_PAYMENT_METHODS}</b>"


def _promotions_text(lang: str) -> str:
    if CURRENT_PROMOTIONS:
        return f"🎁 {CURRENT_PROMOTIONS}"
    if lang == "ru":
        return (
            "На данный момент уточняйте актуальные акции по телефону — "
            "мы часто радуем постоянных клиентов приятными предложениями! 🎁"
        )
    return (
        "Наразі уточнюйте актуальні акції за телефоном — "
        "ми часто радуємо постійних клієнтів приємними пропозиціями! 🎁"
    )


def _unconfigured_service_text(lang: str) -> str:
    if lang == "ru":
        return (
            "По этой процедуре лучше уточнить точную цену и время у мастера "
            "лично — напишите нам или нажмите «📅 Записаться», и администратор "
            "всё подскажет! 💕"
        )
    return (
        "Щодо цієї процедури краще уточнити точну ціну й час у майстра "
        "особисто — напишіть нам або натисніть «📅 Записатися», і "
        "адміністратор все підкаже! 💕"
    )


def _current_time_text(lang: str) -> str:
    now = datetime.now(_TZ)
    time_str = now.strftime("%H:%M")
    if lang == "ru":
        return f"🕐 Сейчас в Киеве: <b>{time_str}</b>\n\n{_hours_text('ru')}"
    return f"🕐 Зараз у Києві: <b>{time_str}</b>\n\n{_hours_text('uk')}"


def _duration_text(service_id: Optional[str], lang: str) -> str:
    """Answers 'how long does it take' — uses the contextually last-mentioned
    service if one was provided (e.g. a one-word follow-up like 'а сколько
    по времени?' right after asking about a specific service), otherwise
    gives a short overview of every service's duration."""
    if service_id:
        svc = SERVICES_MAP.get(service_id)
        if svc:
            if lang == "ru":
                return f"⏱ {svc.name_for('ru')} занимает примерно <b>{svc.duration}</b>."
            return f"⏱ {svc.name_for('uk')} триває приблизно <b>{svc.duration}</b>."
    if lang == "ru":
        lines = ["⏱ <b>Длительность услуг:</b>\n"]
        for s in SERVICES:
            lines.append(f"{s.emoji} {s.name_for('ru')}: {s.duration}")
        return "\n".join(lines)
    lines = ["⏱ <b>Тривалість послуг:</b>\n"]
    for s in SERVICES:
        lines.append(f"{s.emoji} {s.name_for('uk')}: {s.duration}")
    return "\n".join(lines)


def detect_service_mention(question: str) -> Optional[str]:
    """Public helper: does this message name a specific service? Used by the
    handler layer to maintain a tiny, temporary 'last mentioned service'
    context across consecutive AI-mode messages — cleared the instant the
    user leaves AI mode, never touching OpenAI, never stored in the
    database."""
    q_lower = question.lower()
    words = _tokenize(question)
    for svc in SERVICES:
        synonyms = _SERVICE_SYNONYMS.get(svc.id, [svc.name.lower()])
        if _matches(q_lower, words, synonyms):
            return svc.id
    return None


def _howru_text(lang: str, user_id: int) -> str:
    options_ru = [
        "Всё прекрасно, спасибо! 😊 А у вас? Чем можем помочь?",
        "Отлично, готовы помочь вам с любым вопросом о салоне! ✨",
        "Замечательно! Расскажите, чем можем быть полезны? 💕",
    ]
    options_uk = [
        "Все чудово, дякую! 😊 А у вас? Чим можемо допомогти?",
        "Прекрасно, готові допомогти з будь-яким питанням про салон! ✨",
        "Чудово! Розкажіть, чим можемо бути корисні? 💕",
    ]
    return _pick(options_ru if lang == "ru" else options_uk, user_id)


def _greeting_text(lang: str, user_id: int) -> str:
    options_ru = [
        f"Привет! 👋 Рады видеть вас в {SALON_NAME}! Чем можем помочь?",
        f"Здравствуйте! 😊 {SALON_NAME} на связи — спрашивайте что угодно!",
        "Привет-привет! ✨ Готовы ответить на любой вопрос о салоне!",
    ]
    options_uk = [
        f"Привіт! 👋 Раді бачити вас у {SALON_NAME}! Чим можемо допомогти?",
        f"Доброго дня! 😊 {SALON_NAME} на зв'язку — запитуйте будь-що!",
        "Привіт-привіт! ✨ Готові відповісти на будь-яке питання про салон!",
    ]
    return _pick(options_ru if lang == "ru" else options_uk, user_id)


def _aftercare_text(lang: str) -> str:
    if lang == "ru":
        return (
            "После процедуры мастер обязательно расскажет, как ухаживать "
            "за результатом дома — это зависит от конкретной услуги. "
            "Если вопрос актуален прямо сейчас, лучше позвоните нам! 💕"
        )
    return (
        "Після процедури майстер обов'язково розповість, як доглядати "
        "за результатом вдома — це залежить від конкретної послуги. "
        "Якщо питання актуальне зараз, краще зателефонуйте нам! 💕"
    )


def _specialists_text(lang: str) -> str:
    if lang == "ru":
        return (
            "У нас работают только сертифицированные мастера с опытом — "
            "подбор конкретного специалиста уточняется при записи. "
            "Нажмите «📅 Записаться», и администратор поможет с выбором! 💕"
        )
    return (
        "У нас працюють тільки сертифіковані майстри з досвідом — "
        "підбір конкретного фахівця уточнюється під час запису. "
        "Натисніть «📅 Записатися», і адміністратор допоможе з вибором! 💕"
    )


def _gift_certificate_text(lang: str) -> str:
    if lang == "ru":
        phones = "\n".join(f"📞 {p}" for p in SALON_PHONES)
        return f"🎁 Подарочные сертификаты можно оформить по телефону:\n{phones}"
    phones = "\n".join(f"📞 {p}" for p in SALON_PHONES)
    return f"🎁 Подарункові сертифікати можна оформити за телефоном:\n{phones}"


# ── Intent definitions ───────────────────────────────────────────────────────────
#
# Checked in order; the first confident match wins and OpenAI is skipped
# entirely. Order matters: more specific intents (a named service) are
# checked before generic ones (general price/contact questions).

_PRICE_KW = ["ціна", "цін", "прайс", "коштує", "вартість", "скільки коштує",
             "цена", "стоит", "стоимост", "почем", "сколько стоит"]
_HOURS_KW = ["час роботи", "графік", "коли працю", "відкрит", "закрит", "робочі години",
             "до якої", "з якої", "часы работы", "график", "когда работа", "открыт",
             "закрыт", "рабочие часы", "до которого", "со скольки", "до скольки"]
_ADDRESS_KW = ["адрес", "де ви", "де знаходит", "локац", "як доїхати", "де салон",
               "де ти", "где вы", "где находит", "как доехать", "куда идти", "куда ехать"]
_PHONE_KW = ["телефон", "номер", "зв'язатися", "зателефонувати", "контакт",
             "связаться", "позвонить", "позвонити", "кому написат", "кому напис",
             "куда писать", "де писати", "де написати"]
_BOOKING_KW = ["запис", "забронюва", "хочу прийти", "можна прийти", "вільний час",
               "вільне місце", "вільн", "запись", "забронировать", "свободное время",
               "свободно", "свободн", "можно прийти", "хочу записаться", "є запис",
               "есть запись", "есть свобод", "є вільн"]
_CANCEL_KW = ["скасувати запис", "скасувати моя", "відмінити запис", "отменить запись",
              "отмена записи", "как отменить", "як скасувати"]
_MY_BOOKING_KW = ["мій запис", "моя запись", "моя бронь", "перевірити запис", "проверить запись"]
_ABOUT_KW = ["хто ви", "про салон", "розкажіть про", "історія", "давно працю",
             "кто вы", "о салоне", "расскажите о", "история", "давно работа", "досвід", "опыт"]
_GREETING_KW = ["привіт", "вітаю", "доброго дня", "добрий день", "добрий вечір",
                "доброго ранку", "доброго вечора", "привет", "здравствуйте",
                "добрый день", "добрый вечер", "доброе утро", "братан", "брат",
                "хай", "hi", "hello", "йо"]
_HOWRU_KW = ["як справи", "як ти", "як діла", "як життя", "як дела",
             "как дела", "как ты", "что нового", "що нового", "как жизнь"]
_TIME_KW = ["скільки часу", "котра година", "яка година", "сколько времени",
            "который час", "какое время сейчас", "скільки годин зараз"]
_DURATION_KW = ["скільки часу займає", "скільки триває", "як довго триває", "скільки хвилин",
                "скільки по часу", "по времени", "сколько времени займет",
                "сколько времени занимает", "сколько длится", "как долго длится",
                "сколько минут", "скільки часу триває"]
_SOCIAL_KW = ["instagram", "інстаграм", "инстаграм", "телеграм канал", "соцмереж",
              "соцсет", "социальные сети", "соціальні мережі"]
_PAYMENT_KW = ["оплата", "оплатить", "оплатити", "способи оплати", "способы оплаты",
               "картою", "картой", "готівк", "наличны", "безготів", "безналич", "apple pay", "google pay"]
_PROMO_KW = ["акці", "знижк", "скидк", "акции", "промокод", "промо код"]
_AFTERCARE_KW = ["рекомендац", "догляд", "уход", "после процедур", "після процедур",
                 "як доглядати", "как ухаживать"]
_SPECIALISTS_KW = ["майстер", "майстри", "спеціаліст", "мастер", "мастера",
                    "специалист", "косметолог", "стиліст", "стилист"]
_GIFT_KW = ["сертифікат", "сертификат", "подарунков", "подарочн"]
_PARKING_KW = ["паркінг", "парковк", "паркинг", "де поставити машину", "где поставить машину"]


def _knowledge_base_answer(
    question_lower: str, words: List[str], lang: str, user_id: int, context_service_id: str = ""
) -> Optional[str]:
    # Most specific first: a named service.
    for svc in SERVICES:
        synonyms = _SERVICE_SYNONYMS.get(svc.id, [svc.name.lower()])
        if _matches(question_lower, words, synonyms):
            return _service_card(svc.id, lang)

    if _matches(question_lower, words, _UNCONFIGURED_SERVICE_KEYWORDS):
        return _unconfigured_service_text(lang)

    if _matches(question_lower, words, _CANCEL_KW):
        return _cancellation_text(lang)
    if _matches(question_lower, words, _MY_BOOKING_KW):
        return _my_booking_text(lang)
    if _matches(question_lower, words, _DURATION_KW):
        return _duration_text(context_service_id, lang)
    if _matches(question_lower, words, _PRICE_KW):
        return _price_list(lang)
    if _matches(question_lower, words, _HOURS_KW):
        return _hours_text(lang)
    if _matches(question_lower, words, _TIME_KW):
        return _current_time_text(lang)
    if _matches(question_lower, words, _ADDRESS_KW):
        return _address_text(lang)
    if _matches(question_lower, words, _PARKING_KW):
        return (
            "Уточнюйте, будь ласка, про паркування за телефоном — "
            "ми підкажемо найближчі варіанти 🚗" if lang == "uk" else
            "Уточняйте, пожалуйста, о парковке по телефону — "
            "подскажем ближайшие варианты 🚗"
        )
    if _matches(question_lower, words, _PHONE_KW):
        return _phones_text(lang)
    if _matches(question_lower, words, _SOCIAL_KW):
        return _social_text(lang)
    if _matches(question_lower, words, _PAYMENT_KW):
        return _payment_text(lang)
    if _matches(question_lower, words, _PROMO_KW):
        return _promotions_text(lang)
    if _matches(question_lower, words, _GIFT_KW):
        return _gift_certificate_text(lang)
    if _matches(question_lower, words, _AFTERCARE_KW):
        return _aftercare_text(lang)
    if _matches(question_lower, words, _SPECIALISTS_KW):
        return _specialists_text(lang)
    if _matches(question_lower, words, _BOOKING_KW):
        return _booking_text(lang)
    if _matches(question_lower, words, _ABOUT_KW):
        return _about_text(lang)
    if _matches(question_lower, words, _HOWRU_KW):
        return _howru_text(lang, user_id)
    if _matches(question_lower, words, _GREETING_KW):
        return _greeting_text(lang, user_id)

    return None


def _generic_nudge(lang: str, user_id: int) -> str:
    options_uk = [
        "На жаль, я не знайшов точної відповіді на ваше запитання 🙏\n\n"
        "Спробуйте кнопки меню — «💰 Прайс», «📍 Контакти» — або натисніть "
        "«📅 Записатися», і наш майстер відповість особисто! 💕",

        "Хм, не зовсім зрозумів(ла) питання 🙂 Можливо, вас цікавлять послуги, "
        "ціни чи графік роботи? Або просто натисніть «📅 Записатися» — "
        "адміністратор детально все розповість! ✨",

        "Вибачте, я спеціалізуюсь саме на питаннях про салон 💅 Запитайте про "
        "послуги, прайс чи контакти — або скористайтеся кнопками меню нижче 👇",
    ]
    options_ru = [
        "К сожалению, я не нашёл точного ответа на ваш вопрос 🙏\n\n"
        "Попробуйте кнопки меню — «💰 Цены», «📍 Контакты» — или нажмите "
        "«📅 Записаться», и наш мастер ответит лично! 💕",

        "Хм, не совсем понял(а) вопрос 🙂 Возможно, вас интересуют услуги, "
        "цены или график работы? Или просто нажмите «📅 Записаться» — "
        "администратор всё подробно расскажет! ✨",

        "Извините, я специализируюсь именно на вопросах о салоне 💅 Спросите "
        "об услугах, ценах или контактах — или воспользуйтесь кнопками меню ниже 👇",
    ]
    return _pick(options_ru if lang == "ru" else options_uk, user_id)


# ── OpenAI (last resort, only for genuinely unmatched questions) ────────────────

def _system_prompt(lang: str) -> str:
    """Deliberately short: only what's needed to ground facts and set tone —
    no chat history, single-turn, minimal tokens per the project's
    token-efficiency requirement."""
    services_line = ", ".join(f"{s.name_for(lang)} ({s.price})" for s in SERVICES)
    if lang == "ru":
        return (
            f"Ты — администратор салона красоты «{SALON_NAME}». "
            f"Адрес: {SALON_ADDRESS}. Телефоны: {', '.join(SALON_PHONES)}. "
            f"Часы: {SALON_HOURS}. Услуги: {services_line}. "
            "Отвечай ТОЛЬКО на русском, 2-3 предложения, дружелюбно. "
            "Не выдумывай факты, которых нет выше. Предлагай записаться."
        )
    return (
        f"Ти — адміністратор салону краси «{SALON_NAME}». "
        f"Адреса: {SALON_ADDRESS}. Телефони: {', '.join(SALON_PHONES)}. "
        f"Години: {SALON_HOURS}. Послуги: {services_line}. "
        "Відповідай ТІЛЬКИ українською, 2-3 речення, дружньо. "
        "Не вигадуй факти, яких немає вище. Пропонуй записатися."
    )


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

    async def _ask_openai(self, question: str, lang: str) -> Optional[str]:
        """Single short call, no history. Returns None on any failure so the
        caller can fall back to the knowledge base — never raises."""
        if not self._enabled or self._client is None:
            return None

        for attempt in range(2):  # short retry budget — this is a last resort, not the main path
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": _system_prompt(lang)},
                        {"role": "user", "content": question[:300]},
                    ],
                    max_tokens=180,
                    temperature=0.6,
                )
                content = response.choices[0].message.content
                answer = (content or "").strip()
                if answer:
                    return answer
                return None
            except Exception as exc:
                logger.warning(
                    "OpenAI attempt %d/2 failed (%s): %s", attempt + 1, type(exc).__name__, exc
                )
                if attempt == 0:
                    await asyncio.sleep(0.8)
        logger.error("OpenAI unavailable for this question — using knowledge base.")
        return None

    async def ask(
        self,
        question: str,
        user_id: int = 0,
        fallback_lang: str = "uk",
        context_service_id: str = "",
    ) -> str:
        question = (question or "").strip()
        if not question:
            return _generic_nudge(fallback_lang, user_id)

        lang = detect_language(question) or fallback_lang
        q_lower = question.lower()
        words = _tokenize(question)

        # 1 — instant local answer, zero OpenAI tokens spent.
        kb_answer = _knowledge_base_answer(q_lower, words, lang, user_id, context_service_id)
        if kb_answer:
            return kb_answer

        # 2 — genuinely open-ended: try OpenAI once, briefly.
        openai_answer = await self._ask_openai(question, lang)
        if openai_answer:
            return openai_answer

        # 3 — last resort, still varied, still in the right language.
        return _generic_nudge(lang, user_id)
