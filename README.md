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
```
pip install -r requirements.txt
python bot.py
```

### 4. Deploy
Railway.app yoki Render.com (worker, `Procfile` bor).
