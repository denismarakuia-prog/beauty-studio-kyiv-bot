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

# How many days ahead a client may book (today counts as day 0)
BOOKING_WINDOW_DAYS: int = 14

# Minimum lead time before a slot becomes bookable "today" (minutes from now)
MIN_LEAD_TIME_MINUTES: int = 60

# Ukrainian short weekday names (Mon=0 .. Sun=6), used in the date picker
WEEKDAYS_UA: List[str] = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]

# Ukrainian month names (genitive form, for "20 червня")
MONTHS_UA: List[str] = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
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
    ),
]

# Quick-access dict for O(1) lookup
SERVICES_MAP: dict[str, ServiceInfo] = {s.id: s for s in SERVICES}
