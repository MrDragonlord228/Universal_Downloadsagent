
import os
import asyncio
import tempfile
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, Update, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
)
from aiogram.filters import CommandStart
from yt_dlp import YoutubeDL

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"].rstrip("/")
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

pending = {}

QUALITY = {
    "best": "bestvideo+bestaudio/best",
    "720": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "1080": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "1440": "bestvideo[height<=1440]+bestaudio/best[height<=1440]",
    "2160": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
}

def quality_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="720p", callback_data="q:720"),
            InlineKeyboardButton(text="1080p", callback_data="q:1080"),
        ],
        [
            InlineKeyboardButton(text="2K", callback_data="q:1440"),
            InlineKeyboardButton(text="4K", callback_data="q:2160"),
        ],
        [
            InlineKeyboardButton(text="Максимум", callback_data="q:best"),
        ]
    ])


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "👋 Привет! Я Universal Downloads Agent.\n\n"
        "Отправь мне ссылку на видео, чтобы начать скачивание."
    )


@dp.message(F.text)
async def get_link(message: Message):
    url = message.text.strip()

    if not url.startswith(("https://", "http://")):
        await message.answer("❌ Отправь корректную ссылку.")
        return

    pending[message.from_user.id] = url

    await message.answer(
        "🎬 Выбери качество видео:",
        reply_markup=quality_menu()
    )


@dp.callback_query(F.data.startswith("q:"))
async def download_video(callback: CallbackQuery):
    user_id = callback.from_user.id
    url = pending.get(user_id)

    if not url:
        await callback.answer("Сначала отправь ссылку!", show_alert=True)
        return

    quality = callback.data.split(":")[1]
    await callback.answer()

    status = await callback.message.answer(
        "⏳ Начинаю загрузку. Подожди немного..."
    )

    try:
        with tempfile.TemporaryDirectory() as temp:
            output = str(Path(temp) / "video.%(ext)s")

            options = {
                "format": QUALITY[quality],
                "outtmpl": output,
                "merge_output_format": "mp4",
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 30,
                "retries": 2,
            }

            def download():
                with YoutubeDL(options) as ydl:
                    ydl.download([url])

            await asyncio.to_thread(download)

            files = list(Path(temp).glob("video.*"))
            files = [f for f in files if f.is_file()]

            if not files:
                raise Exception("Не удалось получить видео.")

            video = files[0]

            # Облачный Telegram Bot API: ограничение около 50 МБ
            if video.stat().st_size > 49 * 1024 * 1024:
                await status.edit_text(
                    "⚠️ Видео получилось больше 49 МБ.\n"
                    "Попробуй выбрать более низкое качество."
                )
                return

            await status.edit_text("📤 Отправляю видео...")

            await callback.message.answer_video(
                FSInputFile(video),
                caption=f"✅ Готово! Качество: {quality}"
            )

            await status.delete()

    except Exception as error:
        print("Download error:", repr(error))
        await status.edit_text(
            "❌ Не удалось скачать видео.\n"
            "Возможно, сайт не поддерживается или ограничивает загрузку."
        )


async def home(request):
    return web.Response(text="Universal Downloads Agent is running!")


async def webhook(request):
    if request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    ) != WEBHOOK_SECRET:
        raise web.HTTPUnauthorized()

    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)

    return web.Response(text="OK")


async def on_startup(app):
    await bot.set_webhook(
        f"{WEBHOOK_URL}/webhook",
        secret_token=WEBHOOK_SECRET
    )


async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()


app = web.Application()
app.router.add_get("/", home)
app.router.add_post("/webhook", webhook)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)


if __name__ == "__main__":
    web.run_app(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
