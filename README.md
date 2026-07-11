# Life Manager

A private personal system where you capture life through Telegram and retain it in organized, editable Notion databases.

```text
You ⇄ Telegram bot ⇄ Life Manager service ⇄ Notion
                         ├─ local reminder schedule
                         └─ optional AI message formatter
```

The system creates five Notion databases beneath one page: **Tasks**, **Expenses**, **Notes**, **Journal**, and **Goals**. You can read and edit them normally in Notion. Telegram commands and daily summaries query Notion live, so direct Notion edits are respected.

## What you need to provide

Do **not** paste any of these secrets into chat or commit them to Git. Put them only in your local `.env` file.

| Item | Why it is needed | How to get it |
|---|---|---|
| Telegram bot token | Lets the app receive and send messages as your bot | In Telegram, open **@BotFather**, run `/newbot`, follow the naming prompts, and copy the token. |
| Your Telegram numeric user ID | Makes the bot private: every other sender is ignored | Start a chat with your new bot, send `hello`, then run `python -m scripts.get_telegram_id`. |
| Notion connection token | Lets the app create and read your databases | In Notion, create an internal connection/integration and copy its secret token. Enable **Read content** and **Insert content** capabilities. |
| Notion parent-page ID | Tells the setup tool where to create the five databases | Create a blank Notion page called `Life Manager`, copy its link, and take the final 32-character page ID from the URL. |
| OpenAI API key (optional) | Lets messages such as “remind me about insurance next Thursday” become structured records | Create an API key in your OpenAI Platform project. Without it, slash commands and basic captures still work. |
| Public HTTPS address | Needed only for always-on Telegram webhook use | Deploy the included Docker service to a host you control, then use its HTTPS URL as `BASE_URL`. |
| Dashboard password | Protects the dashboard when it is publicly reachable | Make a long, unique password yourself; set `DASHBOARD_PASSWORD`. |

After creating the Notion connection, open your new `Life Manager` page in Notion, click **••• → Add connections**, and select that connection. The setup command will otherwise receive a Notion “not found” permission error.

## First-time setup (Windows PowerShell)

### 1. Prepare the local project

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` in a text editor. Initially add only your `TELEGRAM_BOT_TOKEN`, `NOTION_TOKEN`, and `NOTION_PARENT_PAGE_ID`. Set your timezone if it is not `Asia/Kolkata`.

### 2. Make the Notion structure automatically

```powershell
python -m scripts.setup_notion
```

This creates the five databases under the page you shared with the Notion connection and writes their data-source IDs into `.env`. You do not need to copy database IDs manually.

### 3. Lock the bot to your Telegram account

1. In Telegram, open your new bot and tap **Start**.
2. Send it `hello`.
3. Run:

```powershell
python -m scripts.get_telegram_id
```

The command saves the Telegram user ID into `.env` automatically, restricting the bot to the account that started it.

### 4. Enable intelligent natural-language formatting (recommended)

Add an `OPENAI_API_KEY` to `.env`. The app sends `store: false` with parsing requests and asks the model for strict structured JSON. Treat API use as a conscious privacy choice: do not send passwords, OTPs, recovery codes, or sensitive financial/medical documents through this bot.

### 5. Add security values

Generate a webhook secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put the output in `TELEGRAM_WEBHOOK_SECRET`. Before making the dashboard public, also set a unique `DASHBOARD_PASSWORD`.

## Run it

### Local use — no Docker, domain, or webhook

The default `TELEGRAM_MODE=polling` lets your computer pull messages directly from Telegram. No public URL is needed. Keep this terminal open whenever you want Telegram capture, reminders, and daily summaries to run.

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard). The dashboard lets you test a capture, see setup status, inspect recent records, and view app-managed reminders.

### Later: always-on Telegram use

Telegram needs to reach a public HTTPS endpoint. Deploy with Docker on a service or VPS you control:

```powershell
docker compose up -d --build
```

Set `APP_ENV=production` and `BASE_URL=https://your-domain.example` in `.env`, restart the deployment, then register the webhook:

```powershell
python -m scripts.register_webhook
```

Alternatively, use the dashboard’s **Register webhook** endpoint after deployment. Telegram webhooks require HTTPS and use the secret header configured above. Do not use polling and a webhook at the same time.

## What to send the bot

Natural-language examples (with an AI key):

```text
Buy milk and eggs tomorrow
Spent ₹450 on dinner today
Journal: I felt clear-headed after my morning walk
Remind me to renew car insurance on 2026-08-02
What do I need to do today?
```

Reliable command alternatives (even without an AI key):

```text
/task Pay electricity bill
/expense ₹450 dinner
/note A small idea worth remembering
/journal I am proud I made time to rest.
/goal Run a half marathon
/today
/summary
/reminders
```

An explicit reminder with a date but no time defaults to 09:00 in your configured timezone. The daily task brief defaults to 08:00; change `DAILY_SUMMARY_TIME` in `.env`.

## Privacy model

- Telegram access is restricted by your numeric user ID.
- The Telegram webhook verifies Telegram’s configured secret header.
- Notion gets a narrowly scoped connection: only the page you share is accessible.
- API keys stay in `.env`, which is ignored by Git.
- Notion contains your actual personal records. The app’s SQLite file keeps only processing IDs, record titles/links, and reminder delivery state.
- Telegram bots are not end-to-end encrypted. Keep passwords, one-time codes, recovery codes, and highly sensitive documents out of the bot.

## Checks

Run the parser tests:

```powershell
python -m pytest
```

The app’s `/health` endpoint confirms that the service is running. The dashboard’s **Test connections** action verifies your configured Telegram bot and Notion Tasks data source without storing a new life record.
