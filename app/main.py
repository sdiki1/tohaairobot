from __future__ import annotations

import asyncio
import contextlib
import logging

import uvicorn

from app.admin_panel import create_admin_app
from app.config import load_settings
from app.rag import KnowledgeBase
from app.telegram_bot import SupportTelegramBot
from app.vertex_client import VertexClient


async def async_main() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger = logging.getLogger("app.main")

    settings.attach_dir.mkdir(parents=True, exist_ok=True)

    kb = KnowledgeBase(
        attach_dir=settings.attach_dir,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        top_k_chunks=settings.top_k_chunks,
    )
    stats = await kb.rebuild()
    logger.info(
        "Index rebuilt: files=%s chunks=%s",
        stats.files_count,
        stats.chunks_count,
    )

    vertex_client = VertexClient(settings=settings)
    bot_service = SupportTelegramBot(
        bot_token=settings.bot_token,
        kb=kb,
        vertex_client=vertex_client,
        public_base_url=settings.public_base_url,
    )
    admin_app = create_admin_app(settings=settings, kb=kb)

    uvicorn_config = uvicorn.Config(
        app=admin_app,
        host=settings.admin_host,
        port=settings.admin_port,
        log_level=settings.log_level,
    )
    server = uvicorn.Server(uvicorn_config)

    bot_task = asyncio.create_task(bot_service.start(), name="telegram-bot")
    admin_task = asyncio.create_task(server.serve(), name="admin-panel")

    done, pending = await asyncio.wait(
        {bot_task, admin_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    first_exc: Exception | None = None
    for task in done:
        try:
            _ = task.result()
        except Exception as exc:  # noqa: BLE001
            first_exc = exc
            logger.exception("Task %s failed", task.get_name(), exc_info=exc)

    for task in pending:
        task.cancel()

    with contextlib.suppress(Exception):
        await bot_service.shutdown()
    with contextlib.suppress(Exception):
        server.should_exit = True
    with contextlib.suppress(Exception):
        await asyncio.gather(*pending, return_exceptions=True)

    if first_exc:
        raise first_exc


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
