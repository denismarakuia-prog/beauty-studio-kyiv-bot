# 💅 Beauty Studio Kyiv — Telegram Bot

A production-ready Telegram bot + Mini App for a premium beauty salon.
Built with **Python 3.12 · Aiogram 3.x · FastAPI · SQLite · OpenAI**.

---

## Features

| Feature | Details |
|---|---|
| 🧭 Persistent menu | Always-visible reply keyboard — no `/start` ever needed mid-conversation |
| 📅 Click-only booking | Послуга → Дата → Вільний час → Підтвердження — zero manual typing |
| 🔒 Real slot locking | Database-enforced unique constraint — two clients can never double-book the same slot |
| 📱 One-time contact capture | Native Telegram "share phone" button; asked once, stored forever |
| 📖 My Booking | View and cancel your own active booking any time |
| 🔔 Admin notifications | Instant DM on every new booking *and* every cancellation |
| 💬 AI Assistant | GPT-4o-mini answers questions in Ukrainian, with graceful fallback |
| 🌐 Mini App | Elegant single-page app at `/webapp` — Services, Prices, About, Contacts |
| ⚙️ Admin panel | `/admin`, `/stats`, `/users`, `/leads`, `/export`, `/broadcast` |
| 📤 CSV export | All bookings as UTF-8 BOM CSV (Excel-ready) |
| 🛡 Anti-spam | Outer-middleware throttle, applied before any handler runs |
| 🚦 Race-safe | Slot conflicts are caught and resolved with a fresh picker, never a crash |

---

## Booking flow

```
👤 Client taps "📅 Записатися"
   │
   ├─ Already has an active booking? → shown details + "cancel current" option
   ├─ No phone on file yet?          → one-time "share contact" prompt
   │
   ▼
💄 Оберіть послугу        (inline buttons, one per service)
   ▼
📅 Оберіть дату            (next 14 days, "Сьогодні" / "Завтра" labelled)
   ▼
⏰ Оберіть вільний час     (only times not already booked, with lead-time buffer)
   ▼
📋 Підтвердження           (✅ Підтвердити · ⬅️ Назад · ❌ Скасувати)
   ▼
✅ Saved → admin notified instantly → confirmation shown to client
```

Every step has an inline **⬅️ Назад** to go back one step, and the persistent
reply keyboard underneath means tapping any other menu button always works —
the user can never get stuck inside a flow.

---

## Project structure

```
beauty-studio-kyiv/
├── main.py                       # Entry point — uvicorn + bot polling in one event loop
├── requirements.txt
├── Dockerfile / docker-compose.yml / render.yaml
├── .env.example
├── bot/
│   ├── config.py                 # Env-var configuration
│   ├── salon_data.py             # Salon info, services, prices, scheduling constants
│   ├── core.py                   # Bot + Dispatcher factory, middleware & router wiring
│   ├── database/
│   │   ├── connection.py         # Schema (users, bookings + unique slot-lock index)
│   │   └── repositories.py       # UserRepository, BookingRepository, SlotTakenError
│   ├── handlers/
│   │   ├── start.py              # /start, persistent keyboard, catch-all fallback
│   │   ├── booking.py            # Full click-driven booking FSM
│   │   ├── my_booking.py         # View / cancel active booking
│   │   ├── menu.py                # Price list, About salon
│   │   ├── contacts.py           # Contacts + location pin
│   │   ├── ai_assistant.py       # AI Q&A
│   │   └── admin.py              # Admin panel, broadcast, export
│   ├── keyboards/builders.py     # Reply + inline keyboards, CallbackData schemas
│   ├── middlewares/              # Throttling, user-tracking (outer middleware)
│   └── services/
│       ├── scheduling_service.py # Timezone-aware slot generation (Europe/Kyiv)
│       ├── notification_service.py
│       ├── ai_service.py
│       └── broadcast_service.py
├── api/app.py                    # FastAPI app, lifespan, Mini App routing, /health
└── webapp/index.html             # Telegram Mini App (single file, no build step)
```

---

## Quick start (local)

```bash
git clone <repo> beauty-studio-kyiv
cd beauty-studio-kyiv

cp .env.example .env
# Edit .env: set BOT_TOKEN and optionally OPENAI_API_KEY

docker compose up --build
# or:
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

- API: `http://localhost:8000`
- Mini App: `http://localhost:8000/webapp`
- Health check: `http://localhost:8000/health`

---

## Deploy to Render.com

1. Push the repo to GitHub.
2. Render → **New Web Service** → connect the repo (auto-detects `render.yaml`).
3. Set the secret env vars in the dashboard:
   - `BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
   - `OPENAI_API_KEY` — optional; AI assistant degrades gracefully without it
4. Deploy.
5. Copy the live service URL and set `WEBAPP_URL` = `https://<service>.onrender.com/webapp`, then redeploy.

> **Free tier note:** the filesystem is ephemeral — `bookings`/`users` reset on
> every deploy. For persistence, upgrade to a paid plan and uncomment the
> `disk:` block in `render.yaml`.

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | ✅ | — | Telegram bot token |
| `OPENAI_API_KEY` | — | — | OpenAI key (AI assistant disabled if absent) |
| `ADMIN_IDS` | ✅ | `7520370397` | Comma-separated admin Telegram IDs |
| `DATABASE_PATH` | — | `./data/beauty_studio.db` | SQLite file path |
| `WEBAPP_URL` | — | `` | Full URL to the Mini App (set after first deploy) |
| `OPENAI_MODEL` | — | `gpt-4o-mini` | Any chat-completion model |
| `PORT` | — | `8000` | Set automatically by Render — do not override |
| `LOG_LEVEL` | — | `INFO` | `DEBUG` / `INFO` / `WARNING` |

### Customising for another salon

Edit `bot/salon_data.py` only — no logic changes needed:
salon name/address/phones/hours/about text, the `SERVICES` list, and the
scheduling constants (`OPENING_HOUR`, `CLOSING_HOUR`, `SLOT_STEP_MINUTES`,
`BOOKING_WINDOW_DAYS`, `MIN_LEAD_TIME_MINUTES`, `TIMEZONE_NAME`).

---

## Admin commands

| Command | Description |
|---|---|
| `/admin` | Open admin panel (inline buttons) |
| `/stats` | Users + booking statistics (total, active, today, this week) |
| `/users` | List last 20 users with phone numbers |
| `/leads` | List last 10 bookings (✅ active / ❌ cancelled) |
| `/export` | Download all bookings as CSV |
| `/broadcast` | Send a message to all users |
| `/cancel` | Cancel an active admin flow (e.g. mid-broadcast) |

---

## Tech stack

- **Python 3.12** · **Aiogram 3.7** (polling, FSM, outer middleware)
- **FastAPI + uvicorn** (web server, Mini App, health endpoint)
- **aiosqlite** (async SQLite, WAL mode, partial unique index for slot locking)
- **zoneinfo + tzdata** (correct Europe/Kyiv local time for scheduling)
- **OpenAI SDK** (async, retry + fallback)
- **Docker + Render.com** (free-tier compatible)
