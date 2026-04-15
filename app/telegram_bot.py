from __future__ import annotations

import contextlib
from typing import Final

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from app.rag import KnowledgeBase
from app.vertex_client import VertexClient

TELEGRAM_MESSAGE_LIMIT: Final[int] = 3900


class SupportTelegramBot:
    def __init__(self, bot_token: str, kb: KnowledgeBase, vertex_client: VertexClient, public_base_url: str | None) -> None:
        self._kb = kb
        self._vertex_client = vertex_client
        self._bot = Bot(
            token=bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self._dp = Dispatcher()
        self._register_handlers()

    async def start(self) -> None:
        await self._dp.start_polling(self._bot)

    async def shutdown(self) -> None:
        with contextlib.suppress(Exception):
            await self._dp.stop_polling()
        await self._bot.session.close()

    def _register_handlers(self) -> None:
        @self._dp.message(Command("start"))
        async def start_handler(message: Message) -> None:
            await message.answer(
                "Я бот-консультант по документам из папки attach.\n"
                "Просто напишите вопрос, и я отвечу по найденным инструкциям."
            )

        @self._dp.message(Command("help"))
        async def help_handler(message: Message) -> None:
            await message.answer(
                "Команды:\n"
                "/start - приветствие\n"
                "/help - помощь\n\n"
                "Дальше просто отправляйте вопрос по процессам из документов."
            )

        @self._dp.message(F.text)
        async def question_handler(message: Message) -> None:
            question = (message.text or "").strip()
            if not question:
                await message.answer("Напишите вопрос текстом.")
                return

            await self._bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
            try:
                answer = await self._kb.ask(question=question, vertex_client=self._vertex_client)
            except Exception as exc:
                await message.answer(
                    "Ошибка при обращении к модели Vertex AI. "
                    f"Проверьте ключ/настройки. Детали: {exc}"
                )
                return

            for part in _split_message(answer, TELEGRAM_MESSAGE_LIMIT):
                try:
                    await message.answer(part)
                except Exception:
                    await message.answer(_strip_html(part), parse_mode=None)

        @self._dp.message()
        async def fallback_handler(message: Message) -> None:
            await message.answer("Отправьте текстовый вопрос.")


def _split_message(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]

    lines = text.splitlines(keepends=True)
    chunks: list[str] = []
    current = ""

    for line in lines:
        if len(current) + len(line) <= limit:
            current += line
            continue
        if current:
            chunks.append(current.rstrip())
            current = ""
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        current = line

    if current:
        chunks.append(current.rstrip())
    return chunks


def _strip_html(text: str) -> str:
    return (
        text.replace("<b>", "")
        .replace("</b>", "")
        .replace("<i>", "")
        .replace("</i>", "")
        .replace("<u>", "")
        .replace("</u>", "")
        .replace("<code>", "")
        .replace("</code>", "")
        .replace("<pre>", "")
        .replace("</pre>", "")
    )
