# FarmaciReminder — Blueprint

## 1. Panoramica

Sistema web self-hosted per la gestione delle scadenze dei farmaci personali, con notifiche automatiche su Telegram.

L'utente inserisce i propri farmaci (nome, indicazione, data di scadenza) e il sistema:
- Invia **1 notifica** quando un farmaco entra nella finestra di 30 giorni dalla scadenza
- Invia **1 notifica al giorno** quando un farmaco è scaduto, finché non viene rinnovato o eliminato
- Permette il **rinnovo rapido** della scadenza (dopo l'acquisto di un farmaco nuovo)

- **Stack:** Python + FastAPI, APScheduler, SQLite, HTML + HTMX
- **Modalità bot:** polling Telegram
- **Deployment:** Docker su container Proxmox
- **Backup:** automatico giornaliero
- **Logs:** rotazione FIFO max 10 MB

---

## 2. Stack Tecnologico Dettagliato

| Componente | Scelta | Motivazione |
|------------|--------|-------------|
| Backend | Python + FastAPI | leggero, rapido, supporta API + scheduler |
| Scheduler | APScheduler (CronTrigger) | job giornaliero alle 09:00, affidabile |
| DB | SQLite | sufficiente per uso personale, semplice da gestire |
| Frontend | HTML + HTMX + Jinja2 | leggero, zero complessità JS, rendering server-side |
| Bot | Telegram polling | semplice, nessun HTTPS richiesto |
| Deployment | Docker container | facile backup, restart, upgrade |

---

## 3. Architettura

```
Browser → Frontend HTMX → FastAPI backend → APScheduler (thread separato)
                                  ↘ SQLite (DB persistente)
                                  ↘ Telegram Bot Polling (thread separato)
```

### Scheduler Thread Separato
- Controlla scadenze farmaci ogni giorno alle 09:00
- Esegue un check immediato al boot
- Invia notifiche Telegram per preavviso e scaduto
- Aggiorna stato farmaci nel DB

### Bot Telegram Thread Separato
- Risponde ai comandi /start e /farmaci
- Mostra lista farmaci in scadenza o scaduti su richiesta

---

## 4. Database Schema (SQLite)

### users
| Campo | Tipo | Note |
|-------|------|------|
| id | INTEGER PRIMARY KEY | auto-increment |
| username | TEXT UNIQUE | login |
| password_hash | TEXT | hash sicuro (bcrypt) |
| timezone | TEXT | timezone utente (default Europe/Rome) |
| created_at | TIMESTAMP | data creazione |

### farmaci
| Campo | Tipo | Note |
|-------|------|------|
| id | INTEGER PRIMARY KEY | auto-increment |
| user_id | INTEGER FK | → users.id |
| nome | TEXT | max 100 caratteri |
| descrizione | TEXT | max 500, opzionale — a cosa serve il farmaco |
| data_scadenza | DATE | data di scadenza stampata sulla confezione |
| stato | TEXT | attivo / in_scadenza / scaduto / eliminato |
| notifica_preavviso_inviata | BOOLEAN | preavviso 30gg già inviato (1 sola volta) |
| notifica_scaduto_inviata | BOOLEAN | prima notifica scaduto inviata |
| ultima_notifica_scaduto | DATE | data dell'ultima notifica giornaliera di scaduto |
| created_at | TIMESTAMP | data creazione |
| deleted_at | TIMESTAMP | soft delete |

### settings
| Campo | Tipo | Note |
|-------|------|------|
| key | TEXT PRIMARY KEY | es. telegram_token, telegram_chat_ids |
| value | TEXT | valore configurazione |
| updated_at | TIMESTAMP | ultimo aggiornamento |

### logs
| Campo | Tipo | Note |
|-------|------|------|
| id | INTEGER PRIMARY KEY | auto-increment |
| type | TEXT | INFO / WARN / ERROR |
| message | TEXT | descrizione evento |
| created_at | TIMESTAMP | data creazione |

**Rotazione log**: max 10MB, elimina più vecchi fino a liberare 5MB

---

## 5. Regole Scheduler / Notifiche

### Check scadenze (job giornaliero alle 09:00 + boot)
1. **Preavviso (in scadenza)**:
   - Farmaco con `data_scadenza` entro 30 giorni da oggi
   - `notifica_preavviso_inviata = 0` → invia 1 notifica, poi setta il flag a 1
   - Stato passa a `in_scadenza`
   - **Non reinvia mai** — è un avviso singolo

2. **Scaduto**:
   - Farmaco con `data_scadenza <= oggi`
   - `ultima_notifica_scaduto IS NULL` oppure `< oggi` → invia notifica
   - Aggiorna `ultima_notifica_scaduto` a oggi
   - Stato passa a `scaduto`
   - **Reinvia ogni giorno** finché il farmaco resta scaduto

3. **Rinnovo scadenza** (dall'utente via UI):
   - Aggiorna `data_scadenza` con la nuova data
   - Resetta `notifica_preavviso_inviata = 0`, `notifica_scaduto_inviata = 0`, `ultima_notifica_scaduto = NULL`
   - Stato torna a `attivo`
   - Lo scheduler rivaluterà il farmaco dal prossimo check

### Altre regole
- Farmaci eliminati (soft delete) → scheduler ignora
- Backup DB: ogni 24 ore, mantiene ultimi 7 backup
- Polling Telegram: ogni 2 secondi

---

## 6. Telegram Bot

- Polling bot con token e chat_id autorizzati
- Accetta solo chat_id nella whitelist (configurabile dalla UI)
- Comando `/start` → messaggio di benvenuto
- Comando `/farmaci` → lista farmaci in scadenza e scaduti con dettagli
- Notifiche automatiche inviate dallo scheduler (non dal bot)

### Formato notifiche

**Preavviso:**
```
⚠️ FARMACO IN SCADENZA

💊 Tachipirina 1000mg
📋 Antidolorifico, febbre

📅 Scade il 15/03/2026 (tra 19 giorni)

🔔 Ricordati di rinnovare o sostituire il farmaco.
```

**Scaduto (ripetuta ogni giorno):**
```
🚨 FARMACO SCADUTO

💊 Tachipirina 1000mg
📋 Antidolorifico, febbre

📅 Scaduto il 01/02/2026 (da 23 giorni)

⚠️ Sostituire immediatamente! Non utilizzare farmaci scaduti.
```

---

## 7. Frontend UX

- **Dashboard farmaci** con tabella ordinabile per stato/scadenza/nome
- **Stato farmaci**: badge colorati
  - ✅ Attivo (verde teal)
  - ⚠️ In scadenza (arancione)
  - 🚨 Scaduto (rosso)
  - 🗑️ Eliminato (grigio, barrato)
- **Bordo sinistro colorato** per ogni riga in base allo stato
- **Scadenza**: mostra data + "tra N giorni" o "da N giorni"
- **Azioni per farmaco**:
  - ✏️ Modifica (nome, descrizione, data scadenza)
  - 🗑️ Elimina (con conferma popup)
  - 🔄 Rinnova scadenza (solo per farmaci scaduti — modal rapido con solo la data)
  - ♻️ Ripristina (solo per farmaci eliminati)
- **Filtro**: mostra/nascondi eliminati
- **Tema**: scuro (default) e chiaro, palette medica teal/verde
- **Impostazioni**: modal con tab (Telegram, Tema, Account)

---

## 8. Sicurezza

- Login con username + password
- Cookie session con timeout 24h
- Hash password sicuro (bcrypt)
- Escape HTML e filtraggio input
- Solo chat_id autorizzati ricevono notifiche Telegram

---

## 9. Backup automatico

- Backup giornaliero del file `data/farmaci.db`
- Mantieni ultimi 7 backup nella cartella `data/backups/`

---

## 10. Configurazione centrale

```yaml
# config.yaml
telegram_token: "BOT_TOKEN"
chat_ids:
  - 12345678
polling_interval_sec: 2
log_max_size_mb: 10
log_cleanup_mb: 5
timezone_default: "Europe/Rome"
app_env: "dev"  # dev | prod
```

Token e Chat IDs sono configurabili anche dalla UI (impostazioni), con priorità DB > config.yaml.

---

## 11. API Endpoints

| Metodo | Endpoint | Funzione |
|--------|----------|----------|
| POST | /login | login utente |
| POST | /logout | logout |
| GET | /farmaci | lista farmaci (HTML fragment) |
| POST | /farmaci | aggiungi farmaco |
| PUT | /farmaci/{id} | modifica farmaco / rinnova scadenza |
| DELETE | /farmaci/{id} | soft delete |
| GET | /settings | configurazione Telegram attuale |
| POST | /settings/token | salva token bot |
| POST | /settings/chat-ids | salva chat IDs |
| POST | /settings/test | invia messaggio di test |
| POST | /settings/account | modifica username/password |
| GET | /health | healthcheck |

---

## 12. Struttura cartelle progetto

```text
FarmaciReminder/
├── backend/
│   ├── main.py              # FastAPI app + avvio scheduler e bot
│   ├── database.py          # Schema SQLite e connessione
│   ├── models.py            # Modelli Pydantic
│   ├── auth.py              # Autenticazione + sessioni
│   └── routers/
│       ├── farmaci.py       # CRUD farmaci
│       └── settings.py      # Impostazioni Telegram/Account
├── scheduler/
│   ├── scheduler.py         # APScheduler con cron giornaliero
│   ├── jobs.py              # Logica check scadenze + invio Telegram
│   ├── backup.py            # Backup giornaliero DB
│   └── log_manager.py       # Logging con rotazione FIFO
├── bot/
│   └── bot.py               # Bot Telegram (/start, /farmaci)
├── frontend/
│   ├── index.html           # Dashboard Jinja2 + HTMX
│   ├── partials/
│   │   └── farmaci_list.html    # Fragment lista farmaci
│   └── static/
│       ├── style.css        # Tema medico scuro/chiaro
│       └── icon.png
├── data/                    # DB SQLite e backup
├── logs/                    # Log applicativi
├── docker/                  # Dockerfile e docker-compose
├── config.yaml              # Configurazione centrale
├── requirements.txt
└── README.md
```

---

## 13. Modalità Dev / Prod

- **Dev**: log dettagliati, reload automatico uvicorn
- **Prod**: log puliti, stabile, performance ottimizzata
- Configurabile da `app_env` in config.yaml

---

## 14. Flussi Operativi

### Aggiunta farmaco
1. Dashboard → compila nome, indicazione, data scadenza
2. Backend valida input (escape HTML, check data)
3. Salva su DB con stato `attivo`
4. Lista si aggiorna via HTMX

### Check scadenze (scheduler giornaliero)
1. Scheduler esegue `check_scadenze_farmaci()` alle 09:00
2. Query farmaci attivi/in_scadenza con scadenza entro 30gg → preavviso
3. Query farmaci scaduti senza notifica oggi → notifica giornaliera
4. Invio Telegram + aggiornamento stato/flag nel DB

### Rinnovo farmaco scaduto
1. Utente clicca 🔄 Rinnova sul farmaco scaduto
2. Modal chiede solo la nuova data di scadenza
3. Backend aggiorna data, resetta flag notifiche, stato → attivo
4. Al prossimo check lo scheduler lo rivaluta da zero

### Eliminazione farmaco
1. Utente clicca 🗑️ → popup conferma
2. Soft delete: stato → eliminato, deleted_at = now
3. Ripristinabile con ♻️ (stato → attivo)

---

## 15. UX e Stile

- **Palette medica**: teal/verde (#00bfa5) come primary, sfondo scuro (#0d1117)
- **Tema chiaro**: sfondo #f0f7f6, superfici bianche, bordi teal
- **Badge farmaci**: verde (attivo), arancione (in scadenza), rosso (scaduto), grigio (eliminato)
- **Header**: bordo inferiore teal, emoji 💊, tagline "🏥 Gestione scadenze farmaci"
- **Card aggiunta**: bordo sinistro teal per evidenziare il form
- **Modal**: bordo superiore teal
- **Responsive**: layout colonna singola su mobile, colonne nascoste se necessario

