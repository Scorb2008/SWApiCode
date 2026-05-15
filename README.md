<p align="center">
  <img src="https://img.shields.io/badge/python-3.13-blue?style=for-the-badge&logo=python" alt="Python 3.13">
  <img src="https://img.shields.io/badge/aiogram-3.x-blue?style=for-the-badge&logo=telegram" alt="aiogram 3">
  <img src="https://img.shields.io/badge/FastAPI-0.115-green?style=for-the-badge&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/SQLAlchemy-2.0-red?style=for-the-badge" alt="SQLAlchemy 2.0">
</p>

<h1 align="center">🤖 SWApiCode Bot</h1>

<p align="center">
  Telegram bot for selling Codex API accounts with automatic inventory management,
  balance top‑up via <b>ЮKassa</b>, promo codes, and a full admin panel.
</p>

---

## ✨ Features

### 👤 User
- **🛒 Buy tokens** – choose size, quantity, pay with balance or ЮKassa
- **👤 Profile** – view your ID, balance, purchase count
- **📜 History** – last 15 purchases with details
- **💰 Top‑up** – deposit balance via ЮKassa (40–15 000 ₽)
- **🎟 Promo codes** – activate balance bonuses or token giveaways

### ⚙️ Admin
- **📊 Dashboard** – users, accounts, inventory bar chart by size
- **💰 Revenue** – total, by payment method, last 7/30 days
- **📥 Excel import** – bulk upload accounts from `.xlsx`
- **🔍 User search** – by ID or username
- **👥 User list** – paginated, with card & actions (ban, balance, history)
- **🏷 Promo codes** – create (balance/token), list, delete
- **📢 Broadcast** – send messages (text or photo) to all users
- **📸 Welcome photo** – upload/delete welcome image via admin panel
- **🔔 Payment notifications** – admins get notified on successful ЮKassa payment

---

## 🚀 Quick Start

### Prerequisites
- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (package manager & runner)

### 1. Clone & configure
```bash
git clone <repo-url>
cd SWApiCode
cp .env.example .env
```

Fill in `.env`:
```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_IDS=123456789,987654321

YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key

DATABASE_URL=sqlite+aiosqlite:///data/bot.db
```

### 2. Run locally
```bash
uv sync
uv run bot          # polling mode
uv run api          # FastAPI webhook server (port 8000)
```

### 3. Run with Docker
```bash
docker compose up -d --build
```

---

## 🏗 Project Structure

```
SWApiCode/
├── src/
│   ├── bot/
│   │   ├── __main__.py          # Bot entry point
│   │   ├── bot.py               # Shared Bot instance
│   │   ├── states.py            # FSM states
│   │   ├── handlers/
│   │   │   ├── start.py         # /start handler
│   │   │   ├── user.py          # Buy, profile, history, top‑up, promo
│   │   │   └── admin.py         # Admin panel, dashboard, Excel, broadcast
│   │   └── keyboards/
│   │       └── inline.py        # All inline keyboards
│   ├── api/
│   │   └── app.py               # FastAPI webhook for ЮKassa
│   ├── db/
│   │   ├── database.py          # Async session factory
│   │   ├── models.py            # User, Account, Purchase, PromoCode
│   │   └── repository.py        # All CRUD operations
│   ├── services/
│   │   ├── excel_parser.py      # .xlsx → list[dict]
│   │   ├── yookassa.py          # ЮKassa payment API client
│   │   └── settings.py          # JSON file‑based settings (welcome photo)
│   ├── config.py                # Environment config
│   └── main.py                  # FastAPI app factory + uvicorn runner
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

---

## 🐳 Docker

Two services — `bot` (polling) and `api` (webhook):

```yaml
services:
  bot:      # uv run bot
  api:      # uv run api, port 8000
```

Shared volume `./data:/app/data` for SQLite & settings.

---

## 🔗 ЮKassa Webhook

Set the webhook URL in your ЮKassa account to:
```
https://your-domain.com/yookassa/webhook
```

> ⚠️ Signature verification is not implemented – enable IP whitelist or notification secret in ЮKassa settings.

---

## 📄 License

MIT
