"""
Salon data configuration.
Edit this file (or override via env vars) to customise for a different salon client.
No logic changes required.
"""
from dataclasses import dataclass
from typing import List


# ── Salon identity ─────────────────────────────────────────────────────────────

SALON_NAME: str = "Beauty Studio Kyiv"
SALON_NAME_SHORT: str = "Beauty Studio"
SALON_TAGLINE: str = "Краса і стиль — наша пристрасть"
SALON_ADDRESS: str = "м. Київ, вул. Хрещатик, 22"
SALON_PHONES: List[str] = ["+380 67 451 82 39", "+380 93 774 51 26"]
SALON_HOURS: str = "Щодня 09:00–20:00"
SALON_ABOUT: str = (
    "Beauty Studio Kyiv — це простір, де краса зустрічається з турботою.\n\n"
    "Більше 8 років ми допомагаємо жінкам та чоловікам Києва відчувати себе "
    "впевнено та доглянуто. У нас працюють тільки сертифіковані майстри, "
    "ми використовуємо професійну косметику преміум-класу та суворо "
    "дотримуємось санітарних норм.\n\n"
    "Затишна атмосфера, приємний сервіс та результат, який перевершує "
    "очікування — ось що відрізняє нас від інших."
)
SALON_ABOUT_RU: str = (
    "Beauty Studio Kyiv — это пространство, где красота встречается с заботой.\n\n"
    "Более 8 лет мы помогаем женщинам и мужчинам Киева чувствовать себя "
    "уверенно и ухоженно. У нас работают только сертифицированные мастера, "
    "мы используем профессиональную косметику премиум-класса и строго "
    "соблюдаем санитарные нормы.\n\n"
    "Уютная атмосфера, приятный сервис и результат, который превосходит "
    "ожидания — вот что отличает нас от других."
)

# Google Maps coordinates
SALON_LATITUDE: float = 50.4501
SALON_LONGITUDE: float = 30.5234


# ── Scheduling configuration ────────────────────────────────────────────────────

TIMEZONE_NAME: str = "Europe/Kyiv"

# Salon working hours (24h format)
OPENING_HOUR: int = 9
CLOSING_HOUR: int = 20

# Length of one bookable slot, in minutes
SLOT_STEP_MINUTES: int = 60

# How many full months ahead of the current month a client may book
# (e.g. 4 = current month + 4 more = roughly 4-5 months of availability)
CALENDAR_MONTHS_AHEAD: int = 4

# Minimum lead time before a slot becomes bookable "today" (minutes from now)
MIN_LEAD_TIME_MINUTES: int = 60

# Ukrainian short weekday names (Mon=0 .. Sun=6), used as the calendar header row
WEEKDAYS_UA: List[str] = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]

# Ukrainian month names — genitive form, for inline dates like "20 червня"
MONTHS_UA: List[str] = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]

# Ukrainian month names — nominative form, for calendar titles like "Червень 2026"
MONTHS_UA_NOMINATIVE: List[str] = [
    "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
    "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень",
]


# ── Services ───────────────────────────────────────────────────────────────────

@dataclass
class ServiceInfo:
    id: str
    emoji: str
    name: str
    description: str
    duration: str
    price: str
    # Optional Russian translations, used ONLY by the AI assistant when it
    # detects a Russian-language question. The booking flow never reads
    # these fields and keeps using .name/.description exactly as before —
    # purely additive, zero impact on booking behaviour.
    name_ru: str = ""
    description_ru: str = ""

    def name_for(self, lang: str) -> str:
        return self.name_ru if lang == "ru" and self.name_ru else self.name

    def description_for(self, lang: str) -> str:
        return self.description_ru if lang == "ru" and self.description_ru else self.description


SERVICES: List[ServiceInfo] = [
    ServiceInfo(
        id="manicure",
        emoji="💅",
        name="Манікюр",
        description=(
            "Класичний, гелевий або комбінований манікюр. "
            "Використовуємо матеріали преміум-класу для ідеального та довготривалого результату."
        ),
        duration="60–90 хв",
        price="450–900 грн",
        name_ru="Маникюр",
        description_ru=(
            "Классический, гелевый или комбинированный маникюр. "
            "Используем материалы премиум-класса для идеального и долговременного результата."
        ),
    ),
    ServiceInfo(
        id="pedicure",
        emoji="🦶",
        name="Педикюр",
        description=(
            "Апаратний або SPA-педикюр. Повний догляд за ступнями "
            "з використанням якісних засобів та парафінотерапією."
        ),
        duration="60–120 хв",
        price="550–1 200 грн",
        name_ru="Педикюр",
        description_ru=(
            "Аппаратный или SPA-педикюр. Полный уход за стопами "
            "с использованием качественных средств и парафинотерапией."
        ),
    ),
    ServiceInfo(
        id="haircut",
        emoji="✂️",
        name="Стрижка",
        description=(
            "Жіноча або чоловіча стрижка з укладкою та стайлінгом "
            "від досвідчених майстрів. Індивідуальний підхід до кожного клієнта."
        ),
        duration="45–90 хв",
        price="350–800 грн",
        name_ru="Стрижка",
        description_ru=(
            "Женская или мужская стрижка с укладкой и стайлингом "
            "от опытных мастеров. Индивидуальный подход к каждому клиенту."
        ),
    ),
    ServiceInfo(
        id="coloring",
        emoji="🎨",
        name="Фарбування",
        description=(
            "Будь-який вид фарбування: однотонне, омбре, балаяж, мелірування. "
            "Тільки преміум-фарби та перевірені техніки. Результат, який вражає."
        ),
        duration="120–240 хв",
        price="900–3 500 грн",
        name_ru="Окрашивание",
        description_ru=(
            "Любой вид окрашивания: однотонное, омбре, балаяж, мелирование. "
            "Только премиум-краски и проверенные техники. Результат, который впечатляет."
        ),
    ),
    ServiceInfo(
        id="cosmetology",
        emoji="✨",
        name="Косметологія",
        description=(
            "Чистка обличчя, мезотерапія, пілінги та омолоджуючі процедури. "
            "Доглянута та сяюча шкіра — ваша найкраща прикраса."
        ),
        duration="60–90 хв",
        price="800–2 500 грн",
        name_ru="Косметология",
        description_ru=(
            "Чистка лица, мезотерапия, пилинги и омолаживающие процедуры. "
            "Ухоженная и сияющая кожа — ваше лучшее украшение."
        ),
    ),
]

# Quick-access dict for O(1) lookup
SERVICES_MAP: dict[str, ServiceInfo] = {s.id: s for s in SERVICES}


# ── Optional extra info for the AI assistant ───────────────────────────────────
#
# All optional — leave empty to have the assistant gracefully skip the topic
# (it will invite the client to call/ask in person instead of inventing
# details). None of this affects the booking flow.

SALON_INSTAGRAM: str = ""           # e.g. "@beautystudio_kyiv"
SALON_TELEGRAM_CHANNEL: str = ""    # e.g. "@beautystudio_kyiv_channel"
SALON_PAYMENT_METHODS: str = "Готівка, банківська картка, Apple Pay/Google Pay"
CURRENT_PROMOTIONS: str = ""        # e.g. "−15% на манікюр щовівторка до кінця місяця"
