# myLove — Architecture

Single-file personal AI agent (`bot.py`) running on Telegram.
Uses Claude + ChatGPT with a ReAct tool-calling loop, SQLite memory,
and 7 built-in tools. Designed to be extended by Claude / ChatGPT.

---

## 1. File Layout

```
myLove/
├── bot.py             # entire application
├── requirements.txt   # dependencies
├── Procfile           # worker: python bot.py (Railway / Render)
├── .env.example       # required environment variables
├── .gitignore
├── README.md
├── ARCHITECTURE.md
└── data/              # created at runtime (git-ignored)
    ├── mylove.db      # SQLite: facts(key, value)
    └── user_files/    # uploaded and generated files
```

Runtime creates `data/` automatically on first start.

---

## 2. High-Level Flow

```
Telegram message ──► auth (TELEGRAM_ALLOWED_USER_IDS)
   text   ──► run_agent
   voice  ──► Whisper (OpenAI) ──► run_agent
   photo  ──► GPT-4o vision (direct reply)
   file   ──► saved to data/user_files/

run_agent ──► LLM ──► tool calls? ──yes──► exec_tool ──► back to LLM
                           │
                           no ──► final answer ──► Telegram (split by 4000 chars)
```

---

## 3. ReAct Loop (`run_agent`)

Pseudo-code:

```python
async def run_agent(chat_id, user_text):
    hist = HISTORY.setdefault(chat_id, [])
    hist.append({"role": "user", "content": user_text})

    system = SYSTEM_PROMPT + facts_block()

    for _ in range(10):
        resp = await claude_chat(system, hist)   # or gpt_chat fallback

        if resp["tool_calls"]:
            hist.append({"role": "assistant",
                         "content": resp["content"],
                         "tool_calls": resp["tool_calls"]})
            for tc in resp["tool_calls"]:
                result = await exec_tool(tc["name"], tc["args"])
                hist.append({"role": "tool",
                             "tool_call_id": tc["id"],
                             "content": result})
            continue

        HISTORY[chat_id] = hist[-40:]
        return resp["content"]

    return "Juda ko'p qadam. Vazifani bo'lib yuboring."
```

- Max 10 steps per request; last 40 messages kept per chat.
- Chat history lives in memory only and is lost on restart.

---

## 4. Models

| Situation | Model | Reason |
|---|---|---|
| Default reasoning | `claude-sonnet-4-5` (Anthropic) | Best reasoning + tool calling |
| Fallback if Claude fails | `gpt-4o` (OpenAI) | Resilience |
| If `ANTHROPIC_API_KEY` missing | `gpt-4o` | Only option |
| Vision (photo handler) | `gpt-4o` | Direct OpenAI vision call |
| Voice transcription | `whisper-1` | Only option |
| Image generation | `dall-e-3` | Tool call |

---

## 5. Tools

| Tool | What it does |
|---|---|
| `web_search` | Tavily search, top 5 results |
| `run_python` | Runs code in a subprocess, 30 s timeout |
| `set_fact` / `get_facts` | Long-term memory in SQLite |
| `read_file` / `write_file` | Files inside `data/user_files/` (txt, pdf, xlsx) |
| `generate_image` | DALL-E 3, returns a URL |

Tool definition format (Anthropic style; converted automatically for OpenAI):

```python
{
    "name": "web_search",
    "description": "Search the web. Returns titles and URLs.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"]
    }
}
```

Dispatcher:

```python
async def exec_tool(name, args):
    if name == "web_search":
        ...
    if name == "run_python":
        ...
    ...
    return f"Unknown tool: {name}"
```

To add a tool: append its schema to `TOOLS` and add a branch in `exec_tool`.

---

## 6. Known limits

- `run_python` is not a real sandbox: it runs with the bot's own permissions and environment (including API keys). Keep the bot single-user.
- On Railway/Render the disk is ephemeral unless you attach a volume, so `data/` can be wiped on redeploy.
