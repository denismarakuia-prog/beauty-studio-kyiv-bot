"""
Lightweight i18n for the bot's UI strings (menus, buttons, system messages).

Deliberately NOT a library (gettext/babel/etc) — just a plain dict, in
keeping with the project's "no heavy dependencies" requirement. Covers
every customer-facing screen EXCEPT:
  - the AI assistant's own answers (language-detected per-message and
    generated dynamically in bot/services/ai_service.py, independent of
    the user's saved preference — that's a deliberate, separate mechanism)
  - the step-by-step booking flow (service → calendar → time → confirm)
    and the admin panel, both left exactly as they were, unchanged.

Usage:
    from bot.i18n import t, DEFAULT_LANG
    text = t("welcome", lang)
"""
from __future__ import annotations

from typing import Dict

DEFAULT_LANG = "uk"
SUPPORTED_LANGUAGES = ("uk", "ru")


_STRINGS: Dict[str, Dict[str, str]] = {
    "choose_language": {
        "uk": "🌐 Оберіть мову / Выберите язык:",
        "ru": "🌐 Оберіть мову / Выберите язык:",
    },
    "language_set": {
        "uk": "✅ Мову встановлено: Українська",
        "ru": "✅ Язык установлен: Русский",
    },
    "welcome": {
        "uk": (
            "✨ <b>{salon_name}</b>\n\n"
            "Ласкаво просимо до нашого салону краси ❤️\n\n"
            "Оберіть дію на клавіатурі нижче 👇"
        ),
        "ru": (
            "✨ <b>{salon_name}</b>\n\n"
            "Добро пожаловать в наш салон красоты ❤️\n\n"
            "Выберите действие на клавиатуре ниже 👇"
        ),
    },
    "fallback_unknown": {
        "uk": "Не розумію цю команду 🙂\nСкористайтесь кнопками на клавіатурі нижче 👇",
        "ru": "Не понимаю эту команду 🙂\nВоспользуйтесь кнопками на клавиатуре ниже 👇",
    },
    "stale_button": {
        "uk": "Ця кнопка більше не активна. Скористайтесь меню нижче 👇",
        "ru": "Эта кнопка больше не активна. Воспользуйтесь меню ниже 👇",
    },
    "use_menu_buttons": {
        "uk": "Будь ласка, скористайтесь кнопками на клавіатурі нижче 👇",
        "ru": "Пожалуйста, воспользуйтесь кнопками на клавиатуре ниже 👇",
    },
    "tech_error": {
        "uk": (
            "⚠️ Сталася технічна помилка. Спробуйте, будь ласка, ще раз — "
            "натисніть «📅 Записатися» або скористайтесь меню нижче 👇"
        ),
        "ru": (
            "⚠️ Произошла техническая ошибка. Пожалуйста, попробуйте снова — "
            "нажмите «📅 Записаться» или воспользуйтесь меню ниже 👇"
        ),
    },
    "language_changed": {
        "uk": "✅ Мову змінено на українську.",
        "ru": "✅ Язык изменён на русский.",
    },

    # ── Price list ───────────────────────────────────────────────────────
    "price_title": {
        "uk": "<b>💰 Прайс-лист — {salon_name}</b>\n",
        "ru": "<b>💰 Прайс-лист — {salon_name}</b>\n",
    },
    "price_footer": {
        "uk": "<i>Натисніть «📅 Записатися», щоб обрати послугу, дату й час.</i>",
        "ru": "<i>Нажмите «📅 Записаться», чтобы выбрать услугу, дату и время.</i>",
    },

    # ── About ────────────────────────────────────────────────────────────
    "about_title": {
        "uk": "<b>ℹ️ Про {salon_name}</b>\n\n{about}",
        "ru": "<b>ℹ️ О {salon_name}</b>\n\n{about}",
    },

    # ── Contacts ─────────────────────────────────────────────────────────
    "contacts_block": {
        "uk": "📍 <b>{salon_name}</b>\n\n🏠 {address}\n\n{phones}\n\n🕐 {hours}",
        "ru": "📍 <b>{salon_name}</b>\n\n🏠 {address}\n\n{phones}\n\n🕐 {hours}",
    },

    # ── AI assistant entry ──────────────────────────────────────────────
    "ai_intro": {
        "uk": (
            "💬 <b>Запитайте нашого AI-консультанта</b>\n\n"
            "Напишіть своє питання, і я відповім якомога швидше ✍️\n\n"
            "<i>Можна запитати про послуги, ціни, час роботи або будь-що інше!</i>"
        ),
        "ru": (
            "💬 <b>Спросите нашего AI-консультанта</b>\n\n"
            "Напишите свой вопрос, и я отвечу как можно скорее ✍️\n\n"
            "<i>Можно спросить об услугах, ценах, времени работы или о чём угодно!</i>"
        ),
    },

    # ── My booking ───────────────────────────────────────────────────────
    "my_booking_view": {
        "uk": "📖 <b>Ваш запис</b>\n\n💄 Послуга: {service}\n📅 Дата: {date}\n⏰ Час: {time}",
        "ru": "📖 <b>Ваша запись</b>\n\n💄 Услуга: {service}\n📅 Дата: {date}\n⏰ Время: {time}",
    },
    "my_booking_none": {
        "uk": "📖 У вас немає активних записів.\n\nХочете записатися?",
        "ru": "📖 У вас нет активных записей.\n\nХотите записаться?",
    },
    "my_booking_none_short": {
        "uk": "📖 У вас немає активних записів.",
        "ru": "📖 У вас нет активных записей.",
    },
    "my_booking_db_error": {
        "uk": "⚠️ Сталася помилка. Спробуйте, будь ласка, пізніше.",
        "ru": "⚠️ Произошла ошибка. Пожалуйста, попробуйте позже.",
    },
    "my_booking_cancel_ask": {
        "uk": "❓ <b>Скасувати цей запис?</b>\n\n💄 {service}\n📅 {date}\n⏰ {time}",
        "ru": "❓ <b>Отменить эту запись?</b>\n\n💄 {service}\n📅 {date}\n⏰ {time}",
    },
    "my_booking_not_active": {
        "uk": "Цей запис вже не активний",
        "ru": "Эта запись уже не активна",
    },
    "my_booking_db_error_alert": {
        "uk": "Сталася помилка",
        "ru": "Произошла ошибка",
    },
    "my_booking_left": {
        "uk": "Запис залишено",
        "ru": "Запись оставлена",
    },
    "my_booking_already_cancelled": {
        "uk": "Цей запис вже скасовано",
        "ru": "Эта запись уже отменена",
    },
    "my_booking_db_error_retry": {
        "uk": "Сталася помилка. Спробуйте ще раз.",
        "ru": "Произошла ошибка. Попробуйте ещё раз.",
    },
    "my_booking_cancelled_success": {
        "uk": (
            "✅ <b>Запис скасовано</b>\n\n"
            "Будемо раді бачити вас знову! Натисніть «📅 Записатися», "
            "щоб обрати новий час."
        ),
        "ru": (
            "✅ <b>Запись отменена</b>\n\n"
            "Будем рады видеть вас снова! Нажмите «📅 Записаться», "
            "чтобы выбрать новое время."
        ),
    },
    "btn_cancel_booking": {
        "uk": "❌ Скасувати запис",
        "ru": "❌ Отменить запись",
    },
    "btn_yes_cancel": {
        "uk": "✅ Так, скасувати",
        "ru": "✅ Да, отменить",
    },
    "btn_no_keep": {
        "uk": "↩️ Ні, залишити",
        "ru": "↩️ Нет, оставить",
    },
    "btn_book_now": {
        "uk": "📅 Записатися",
        "ru": "📅 Записаться",
    },
    "cancelled_toast": {
        "uk": "Скасовано",
        "ru": "Отменено",
    },
}


def t(key: str, lang: str, **kwargs) -> str:
    """Look up a translated string; falls back to Ukrainian, then the raw key."""
    entry = _STRINGS.get(key)
    if not entry:
        return key
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def normalize_lang(lang: str | None) -> str:
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANG
