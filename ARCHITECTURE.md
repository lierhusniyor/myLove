# Architecture

Single-file Telegram bot (`bot.py`), long polling, one allowed user.

## Flow
```
Telegram message ──► auth (TELEGRAM_ALLOWED_USER_IDS)
   text   ──► run_agent
   voice  ──► Whisper (OpenAI) ──► run_agent
   photo  ──► GPT-4o vision (direct reply)
   file   ──► saved to data/user_files/
```

## Agent loop (`run_agent`)
1. Append the user message to in-memory `HISTORY[chat_id]` (last 40 kept).
2. Build the system prompt + facts stored in SQLite.
3. Call Claude (`claude-sonnet-4-5`) if `ANTHROPIC_API_KEY` is set, otherwise GPT-4o. On error, fall back to the other model.
4. If the model returns tool calls, run them with `exec_tool`, append results, repeat (max 10 steps).
5. Otherwise return the text (split into 4000-char Telegram messages).

## Tools
| Tool | What it does |
|---|---|
| `web_search` | Tavily search, top 5 results |
| `run_python` | Runs code in a subprocess, 30 s timeout |
| `set_fact` / `get_facts` | Long-term memory in SQLite (`data/mylove.db`) |
| `read_file` / `write_file` | Files inside `data/user_files/` (txt, pdf, xlsx) |
| `generate_image` | DALL-E 3, returns a URL |

## Storage
- `data/mylove.db` — `facts(key, value)`
- `data/user_files/` — uploaded and generated files
- Chat history lives in memory only and is lost on restart.

## Known limits
- `run_python` is not a real sandbox: it runs with the bot's own permissions and environment (including API keys). Keep the bot single-user.
- On Railway/Render the disk is ephemeral unless you attach a volume, so `data/` can be wiped on redeploy.
