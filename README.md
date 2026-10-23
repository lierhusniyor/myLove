# myLove

Personal multi-model AI agent on Telegram. Uses Claude + ChatGPT with tool calling.

## Features
- Multi-model: Claude Sonnet for reasoning, GPT-4o for vision, Whisper for voice
- Tools: web search (Tavily), Python sandbox, file I/O (PDF/Excel/txt), image gen (DALL-E), memory (SQLite)
- Languages: Uzbek, Russian, English
- Single-user locked

## Setup

### 1. Prerequisites
- Telegram bot token: @BotFather
- Your Telegram user ID: @userinfobot
- Anthropic API key: console.anthropic.com
- OpenAI API key: platform.openai.com
- Tavily API key: tavily.com (free tier)

### 2. Configure
Create `.env` file in repo root with:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_IDS=123456789
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
TAVILY_API_KEY=...
```

### 3. Run

**Option A: Railway.app (easiest for phone)**
1. Push code to GitHub
2. railway.app -> New Project -> Deploy from GitHub
3. Select this repo
4. Add environment variables (same as .env)
5. Deploy

**Option B: Render.com**
1. render.com -> New -> Background Worker
2. Connect GitHub repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `python bot.py`
5. Add environment variables
6. Deploy

**Option C: Local**
```bash
pip install -r requirements.txt
python bot.py
```
