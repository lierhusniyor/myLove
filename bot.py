"""myLove — personal multi-model AI agent on Telegram."""
import os
import io
import json
import asyncio
import tempfile
import sqlite3
import base64
from pathlib import Path
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED = {int(x) for x in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if x.strip()}
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_KEY = os.getenv("TAVILY_API_KEY")

DB_PATH = "./data/mylove.db"
USER_FILES = Path("./data/user_files").resolve()
Path("./data").mkdir(exist_ok=True)
USER_FILES.mkdir(parents=True, exist_ok=True)

HISTORY: dict[int, list] = {}


# ---------- DB ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS facts (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()


def get_facts() -> dict:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT key, value FROM facts").fetchall()
    conn.close()
    return dict(rows)


def set_fact(k: str, v: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO facts (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()


# ---------- TOOLS ----------
TOOLS = [
    {"name": "web_search", "description": "Search the web. Returns titles and URLs.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "run_python", "description": "Execute Python code in a sandbox. Returns stdout.",
     "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
    {"name": "set_fact", "description": "Remember a fact about the user.",
     "input_schema": {"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "string"}}, "required": ["key", "value"]}},
    {"name": "get_facts", "description": "List all stored facts.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "read_file", "description": "Read a file from user's storage (txt/pdf/xlsx).",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write text to a file in user's storage.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "generate_image", "description": "Generate an image from a prompt (DALL-E 3). Returns URL.",
     "input_schema": {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]}},
]


async def exec_tool(name: str, args: dict) -> str:
    try:
        if name == "web_search":
            if not TAVILY_KEY:
                return "TAVILY_API_KEY not set."
            from tavily import AsyncTavilyClient
            client = AsyncTavilyClient(api_key=TAVILY_KEY)
            r = await client.search(args["query"], max_results=5)
            return "\n".join(f"- {x['title']}: {x['url']}" for x in r.get("results", [])) or "No results."
        if name == "run_python":
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
                f.write(args["code"])
                p = f.name
            try:
                proc = await asyncio.create_subprocess_exec(
                    "python", p,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
                result = (out.decode() or "")
                if err:
                    result += "\nERR: " + err.decode()
                return result or "(no output)"
            except asyncio.TimeoutError:
                return "Timeout (30s)"
            finally:
                os.unlink(p)
        if name == "set_fact":
            set_fact(args["key"], args["value"])
            return "Saved."
        if name == "get_facts":
            f = get_facts()
            return "\n".join(f"- {k}: {v}" for k, v in f.items()) or "(empty)"
        if name == "read_file":
            p = (USER_FILES / args["path"]).resolve()
            if not str(p).startswith(str(USER_FILES)):
                return "Path denied."
            if not p.exists():
                return "File not found."
            if p.suffix.lower() == ".pdf":
                from pypdf import PdfReader
                return "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages)[:8000]
            if p.suffix.lower() in (".xlsx", ".xls"):
                from openpyxl import load_workbook
                wb = load_workbook(str(p), data_only=True)
                rows = []
                for ws in wb:
                    for row in ws.iter_rows(values_only=True):
                        rows.append("\t".join(str(c) if c is not None else "" for c in row))
                return "\n".join(rows)[:8000]
            return p.read_text(errors="replace")[:8000]
        if name == "write_file":
            p = (USER_FILES / args["path"]).resolve()
            if not str(p).startswith(str(USER_FILES)):
                return "Path denied."
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"])
            return f"Written {len(args['content'])} chars."
        if name == "generate_image":
            if not OPENAI_KEY:
                return "OPENAI_API_KEY not set."
            client = AsyncOpenAI(api_key=OPENAI_KEY)
            r = await client.images.generate(model="dall-e-3", prompt=args["prompt"], size="1024x1024", n=1)
            return r.data[0].url
        return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool error: {e}"


# ---------- SYSTEM PROMPT ----------
SYSTEM_PROMPT = """You are myLove, a personal AI assistant for one user.

## Role
All-purpose assistant. Handle ANY task: research, writing, coding, planning, analysis, images, files, scheduling.
Use tools when needed.

## Languages
User speaks Uzbek, Russian, English. Reply in the same language as the user's message.
For hard reasoning, think in English but reply in user's language.

## Behavior
- Accuracy > speed. Ask if unsure.
- Concise. No filler.
- Warm but professional.

## Tools
- web_search — search the internet
- run_python — execute Python
- set_fact / get_facts — remember info about user
- read_file / write_file — user files
- generate_image — DALL-E 3

## Self-check
Before replying: did I answer fully? Correct language? Right tools?
"""


# ---------- LLM ADAPTERS ----------
async def claude_chat(system: str, messages: list) -> dict:
    client = AsyncAnthropic(api_key=ANTHROPIC_KEY)
    conv = []
    for m in messages:
        if m["role"] == "tool":
            conv.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": str(m["content"])}]})
        elif m["role"] == "assistant" and m.get("tool_calls"):
            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["args"]})
            conv.append({"role": "assistant", "content": blocks})
        else:
            conv.append({"role": m["role"], "content": m["content"]})
    resp = await client.messages.create(
        model="claude-sonnet-4-5", max_tokens=4096,
        system=system or "You are a helpful assistant.",
        messages=conv, tools=TOOLS,
    )
    text = ""
    tools = []
    for b in resp.content:
        if b.type == "text":
            text += b.text
        elif b.type == "tool_use":
            tools.append({"id": b.id, "name": b.name, "args": b.input})
    return {"content": text, "tool_calls": tools}


async def gpt_chat(system: str, messages: list) -> dict:
    client = AsyncOpenAI(api_key=OPENAI_KEY)
    msgs = [{"role": "system", "content": system}]
    for m in messages:
        if m["role"] == "tool":
            msgs.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": str(m["content"])})
        elif m["role"] == "assistant" and m.get("tool_calls"):
            msgs.append({
                "role": "assistant", "content": m.get("content") or None,
                "tool_calls": [{"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])}} for tc in m["tool_calls"]],
            })
        else:
            msgs.append({"role": m["role"], "content": m["content"]})
    tools_oai = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in TOOLS]
    resp = await client.chat.completions.create(model="gpt-4o", messages=msgs, tools=tools_oai)
    msg = resp.choices[0].message
    tools_out = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            tools_out.append({"id": tc.id, "name": tc.function.name, "args": json.loads(tc.function.arguments or "{}")})
    return {"content": msg.content or "", "tool_calls": tools_out}


async def run_agent(chat_id: int, text: str) -> str:
    hist = HISTORY.setdefault(chat_id, [])
    hist.append({"role": "user", "content": text})
    facts = get_facts()
    system = SYSTEM_PROMPT
    if facts:
        system += "\n\nKnown facts about user:\n" + "\n".join(f"- {k}: {v}" for k, v in facts.items())

    for _ in range(10):
        try:
            if ANTHROPIC_KEY:
                resp = await claude_chat(system, hist)
            else:
                resp = await gpt_chat(system, hist)
        except Exception as e:
            try:
                resp = await gpt_chat(system, hist) if ANTHROPIC_KEY else await claude_chat(system, hist)
            except Exception as e2:
                return f"Xatolik: {e} / {e2}"

        if resp.get("tool_calls"):
            hist.append({"role": "assistant", "content": resp.get("content") or "", "tool_calls": resp["tool_calls"]})
            for tc in resp["tool_calls"]:
                r = await exec_tool(tc["name"], tc["args"])
                hist.append({"role": "tool", "tool_call_id": tc["id"], "content": r})
            continue

        final = resp.get("content") or "(empty)"
        HISTORY[chat_id] = hist[-40:]
        return final
    return "Juda ko'p qadam. Iltimos, vazifani bo'lib yuboring."


# ---------- HANDLERS ----------
def auth(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id in ALLOWED)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not auth(update):
        await update.message.reply_text("Ruxsat yo'q.")
        return
    await update.message.reply_text("Salom! Men myLove. Har qanday vazifani bering.\n\n/reset /memory")


async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not auth(update):
        return
    HISTORY[update.effective_chat.id] = []
    await update.message.reply_text("Tozalandi.")


async def cmd_memory(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not auth(update):
        return
    f = get_facts()
    await update.message.reply_text("\n".join(f"- {k}: {v}" for k, v in f.items()) or "(bo'sh)")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not auth(update):
        await update.message.reply_text("Ruxsat yo'q.")
        return
    t = update.message.text or ""
    if not t.strip():
        return
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    r = await run_agent(update.effective_chat.id, t)
    for i in range(0, len(r), 4000):
        await update.message.reply_text(r[i:i+4000])


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not auth(update):
        return
    if not OPENAI_KEY:
        await update.message.reply_text("Ovoz uchun OPENAI_API_KEY kerak.")
        return
    v = update.message.voice or update.message.audio
    f = await ctx.bot.get_file(v.file_id)
    bio = io.BytesIO()
    await f.download_to_memory(bio)
    bio.seek(0)
    bio.name = "v.ogg"
    client = AsyncOpenAI(api_key=OPENAI_KEY)
    try:
        tr = await client.audio.transcriptions.create(model="whisper-1", file=bio)
    except Exception as e:
        await update.message.reply_text(f"Xato: {e}")
        return
    await update.message.reply_text(f"Eshitdim: {tr.text}")
    r = await run_agent(update.effective_chat.id, tr.text)
    for i in range(0, len(r), 4000):
        await update.message.reply_text(r[i:i+4000])


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not auth(update):
        return
    if not OPENAI_KEY:
        await update.message.reply_text("Rasm uchun OPENAI_API_KEY kerak.")
        return
    p = update.message.photo[-1]
    f = await ctx.bot.get_file(p.file_id)
    bio = io.BytesIO()
    await f.download_to_memory(bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    cap = update.message.caption or "Bu rasmda nima bor? Batafsil tushuntir."
    client = AsyncOpenAI(api_key=OPENAI_KEY)
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": [
            {"type": "text", "text": cap},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
    )
    await update.message.reply_text(resp.choices[0].message.content)


async def handle_doc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not auth(update):
        return
    d = update.message.document
    f = await ctx.bot.get_file(d.file_id)
    dest = USER_FILES / (d.file_name or "uploaded.bin")
    await f.download_to_drive(str(dest))
    await update.message.reply_text(f"{dest.name} saqlandi.")


def main():
    init_db()
    app = Application.builder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("myLove bot ishga tushdi...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
