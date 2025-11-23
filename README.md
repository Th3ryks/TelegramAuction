# AuctionState Bot 🛠️🚀

A fully asynchronous Telegram bot that tracks and posts auction state updates to your channel using real data from Telegram's API.

## Features ✨
- Async-first with `asyncio`, `aiohttp`, `aiogram`.
- MarkdownV2-rich messages with collapsible quotes for top bids.
- Smart update cadence: every 60s, and every 30s in the last minute.
- Sends a new message on round change and marks previous as "Round Ended" 🕓.
- Sends an "Auction Finished" message immediately when `end_date` occurs.
- Shows bottom "Last Update" timestamp in UTC.

## Two Versions 🔀
This project includes two complementary ways to publish auction updates:

- Userbot (MTProto) ✨: `userbot.py` posts as a Telegram user using Pyrogram. Uses a custom emoji for clock in messages.
- Bot (Bot API) 🤖: `bot.py` posts as a bot using Aiogram. Uses the standard clock emoji.

Both versions:
- Link to the current auction with a header.
- Edit the previous message to display "Round Ended" when `next_round_at` is reached.
- Immediately send a terminal "Auction Finished" message when `end_date` is reached.
- Append the latest UTC timestamp at the very bottom of the message.

## Requirements 📦
- Python 3.11+
- Environment variables in `.env`:
  - `API_ID`
  - `API_HASH`
  - `BOT_TOKEN`
  - `CHANNEL_ID` (numeric `3441054411`)

## Get the code 📥
```bash
git clone https://github.com/Th3ryks/TelegramAuction.git
cd TelegramAuction
```

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run (Python) 🧑‍💻
```bash
python3 main.py
```

## Run (Docker) 🐳
Create a minimal `Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["python3", "main.py"]
```

Build and run:

```bash
docker build -t auctionstate .
docker run --env-file .env --name auctionstate --rm auctionstate
```

## Links 🔗
- Live bot: [AuctionStateTG](https://t.me/AuctionStateTG)
- Developer: [Th3ryks](https://t.me/nft/Th3ryks)

## Notes 📝
- Start via `python3 main.py`.
- All secrets must be provided via environment variables; never hardcode tokens.
 - `.env` must include real values; no demo data is used.