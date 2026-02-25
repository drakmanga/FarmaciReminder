# 💊 FarmaciReminder

Self-hosted web system for managing medicine expiry dates with automatic Telegram notifications.

Add your medicines with name, purpose and expiry date. The system will automatically alert you when a medicine is about to expire or has already expired.

---

## ✨ Features

- **Medicine management** — add, edit, delete medicines with name, description and expiry date (date is optional)
- **Expiry warning** — automatic Telegram alert **once** when a medicine enters the 30-day window before expiry
- **Expired notification** — Telegram alert **every day** as long as the medicine remains expired
- **Quick renewal** — 🔄 button to update the expiry date of an expired medicine (after purchasing a new one)
- **Web dashboard** — medical-themed interface, sorting by status/expiry, colored badges
- **Search bar** — filter medicines by name directly in the dashboard
- **Expired counter** — badge showing the number of expired medicines with a one-click filter
- **CSV export** — download the full medicine list as a `.csv` file
- **Auto-capitalization** — name and description are automatically capitalized on add/edit
- **Telegram bot** — `/farmaci`, `/lista`, `/cerca` commands (see below)
- **Automatic backup** — daily SQLite database backup
- **Light/dark theme** — toggle available in settings

---

## 🖥️ Installation on Proxmox (Debian CT) — recommended method

### Method A — Automatic (from Proxmox)

Copy the project to the Proxmox node, then run:

```bash
bash create_ct.sh
```

The script will ask for: CT ID, hostname, root password, storage, disk, RAM, CPU, IP, app port.
It will create the CT, copy the project and automatically run `install.sh`.

---

### Method B — Manual (inside an existing CT)

If you already have a Debian 12 CT ready, copy the project folder into the CT and run:

```bash
bash /path/to/project/install.sh
```

The script will ask for: installation directory, HTTP port, secret key, admin username/password, timezone, Telegram token and Chat ID (optional, configurable from the UI).

At the end it installs the **systemd** service (`farmaci_reminder.service`) with automatic startup on boot.

---

### Useful commands after installation

```bash
# Service status
systemctl status farmaci_reminder

# Live logs
journalctl -u farmaci_reminder -f

# Restart
systemctl restart farmaci_reminder

# Application log
tail -f /opt/farmaci_reminder/logs/app.log
```

---

## 📋 Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.11+ / FastAPI |
| Scheduler | APScheduler (daily cron) |
| Database | SQLite |
| Frontend | HTML + HTMX + Jinja2 |
| Bot | Telegram (polling) |
| Deploy | Docker on Proxmox/Debian |

---

## 🚀 Initial Setup

### 1. Configure `config.yaml`

```yaml
telegram_token: "YOUR_BOT_TOKEN"
chat_ids:
  - 12345678       # your Telegram chat_id
timezone_default: "Europe/Rome"
```

To get the token: talk to [@BotFather](https://t.me/BotFather) on Telegram.  
To get your chat_id: talk to [@userinfobot](https://t.me/userinfobot).

### 2. Change default passwords

Edit `backend/auth.py` in the `create_default_users()` function:
- User `admin` → password `admin123`

> ⚠️ **CHANGE THE PASSWORD BEFORE DEPLOYING!**

---

## 💻 Dev mode (local)

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python -m backend.main
```

The system will be available at: **http://localhost:8000**

---

## 🐳 Docker Deploy (Proxmox/Debian)

### Prerequisites
```bash
apt-get update && apt-get install -y docker.io docker-compose
```

### Start

```bash
# 1. Copy the project to the server
scp -r FarmaciReminder/ user@server:/opt/FarmaciReminder/

# 2. Enter the folder
cd /opt/FarmaciReminder

# 3. Create the .env file
cp .env.example .env
# Edit .env with a random secret key

# 4. Start with Docker Compose
cd docker
docker compose up -d --build

# 5. Check logs
docker compose logs -f
```

The system will be available at: **http://SERVER_IP:8000**

### Useful Docker commands

```bash
docker compose down            # stop the container
docker compose restart         # restart
docker compose up -d --build   # update after code changes
docker compose logs -f         # live logs
```

---

## 📁 Project Structure

```
FarmaciReminder/
├── backend/
│   ├── main.py              # FastAPI app + scheduler/bot startup
│   ├── database.py          # SQLite schema and connection
│   ├── models.py            # Pydantic models (FarmacoCreate/Update/Out)
│   ├── auth.py              # Authentication + session management
│   └── routers/
│       ├── farmaci.py       # Medicine CRUD (HTML fragments for HTMX)
│       └── settings.py      # Telegram/Account settings
├── scheduler/
│   ├── scheduler.py         # APScheduler with daily cron
│   ├── jobs.py              # Expiry check logic + Telegram sending
│   ├── backup.py            # Daily DB backup
│   └── log_manager.py       # Logging with FIFO rotation
├── bot/
│   └── bot.py               # Telegram bot (/start, /farmaci)
├── frontend/
│   ├── index.html           # Dashboard (Jinja2 + HTMX)
│   ├── partials/
│   │   └── farmaci_list.html    # Medicine list HTML fragment
│   └── static/
│       ├── style.css        # Medical theme (dark/light)
│       └── icon.png         # Icon
├── data/                    # SQLite DB and backups (persistent)
├── logs/                    # Application logs
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── config.yaml              # ⚙️ Central configuration
├── requirements.txt         # Python dependencies
└── README.md
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/login` | User login |
| POST | `/logout` | Logout |
| GET | `/farmaci` | Medicine list (HTML fragment) |
| POST | `/farmaci` | Add medicine |
| PUT | `/farmaci/{id}` | Edit medicine / renew expiry |
| DELETE | `/farmaci/{id}` | Delete medicine (soft delete) |
| GET | `/export/csv` | Export all medicines as CSV |
| GET | `/settings` | Current Telegram config |
| POST | `/settings/token` | Save bot token |
| POST | `/settings/chat-ids` | Save Chat IDs |
| POST | `/settings/test` | Send test message |
| POST | `/settings/account` | Change username/password |
| GET | `/health` | Healthcheck |

---

## 🗄️ Database Schema

### farmaci (medicines)

| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK | auto-increment |
| user_id | INTEGER FK | → users.id |
| nome | TEXT | max 100 chars — medicine name |
| descrizione | TEXT | max 500, optional — what it's for |
| data_scadenza | DATE | expiry date |
| stato | TEXT | attivo / in_scadenza / scaduto / eliminato |
| notifica_preavviso_inviata | BOOLEAN | 30-day warning sent |
| notifica_scaduto_inviata | BOOLEAN | first expired notification sent |
| ultima_notifica_scaduto | DATE | last daily expired notification date |
| created_at | TIMESTAMP | creation date |
| deleted_at | TIMESTAMP | soft delete |

### Other tables
- **users** — credentials and timezone
- **settings** — Telegram configuration (key/value)
- **logs** — application logs with rotation

---

## ⚙️ Scheduler Rules

- **Expiry check**: every day at **09:00** (Europe/Rome)
- **Boot check**: runs immediately on startup
- **Warning**: 1 single notification when a medicine enters the 30-day expiry window
- **Expired**: 1 notification per day, every day, as long as the medicine remains expired
- **Renewal**: updating the expiry date resets the status to "attivo" and clears all notification flags
- **DB backup**: every 24 hours, keeps the last 7 backups
- **Logs**: FIFO rotation, max 10 MB, cleanup at 5 MB

---

## 🤖 Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/farmaci` | List of expiring and expired medicines |
| `/lista` | Full list of all medicines |
| `/cerca [name]` | Search medicines by name |

Automatic notifications are sent to the chat_ids configured in settings.

---

## 🔒 Security

- Passwords hashed with **bcrypt**
- Sessions with secure cookie, **24h** timeout
- Only authorized chat_ids receive Telegram notifications
- Sanitized input (HTML escape)
- Telegram token stored in `config.yaml` or DB (excluded from git)

---

## 🐛 Troubleshooting

**The bot doesn't send messages:**
- Check that `telegram_token` is correct (config.yaml or UI settings)
- Verify that `chat_ids` are correct
- Send `/start` to the bot first

**Login doesn't work:**
- Default user: `admin` / `admin123`
- If the DB is corrupted: delete `data/farmaci.db` and restart

**Docker: permission denied on data/logs:**
```bash
chmod 755 data/ logs/
```
